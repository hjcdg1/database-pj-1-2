import itertools
import re
from datetime import datetime, date

from lark import Transformer

from src import exceptions
from src.database import DatabaseManager
from src.literals import PROMPT_TEXT

"""
The structure of the data stored in Berkeley DB is as follows.

[table_name]: {
    columns: {
        name: string,
        type: string,
        null: boolean,
        primary: boolean,
        foreign: { table_name: string, column_name: string } | None
    }[],
    records: { [column_name]: int | string }[]
}
"""


class SQLExecutor(Transformer):
    WIDTH_PADDING = 2

    def __init__(self, database):
        super().__init__()
        self.db_manager = DatabaseManager(database)

    def execute(self, tree):
        """
        Rename `transform` method for improving readability
        """

        self.transform(tree)

    @classmethod
    def parse_value(cls, value):
        """
        Parse a SQL input value and return the parsed result
        : SQL input -> Python value
        """

        # null
        if value.lower() == 'null':
            parsed_type = 'null'
            parsed_value = None

        else:
            try:
                # int
                parsed_type = 'int'
                parsed_value = int(value)
            except ValueError:
                # date
                if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                    parsed_type = 'date'
                    parsed_value = datetime.strptime(value, '%Y-%m-%d').date()

                # char
                else:
                    parsed_type = 'char'
                    parsed_value = eval(value)

        return parsed_type, parsed_value

    @classmethod
    def serialize_value(cls, value):
        """
        Serialize a Python value (When storing in the database)
        : Python value -> The value that is stored in the database
        """

        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        else:
            return value

    @classmethod
    def deserialize_value(cls, value, column_type):
        """
        Deserialize a database value (When fetching from the database)
        : The value that is stored in the database -> Python value
        """

        if value is not None and column_type == 'date':
            return datetime.strptime(value, '%Y-%m-%d').date()
        else:
            return value

    def create_table_query(self, items):
        # Extract the table name
        table_name = items[2].children[0].lower()

        # Error: When a table with the same name already exists
        existing_table_name_set = set(self.db_manager.get_table_names())
        if table_name in existing_table_name_set:
            raise exceptions.TableExistenceError

        # Extract the column definitions
        column_list = []
        column_name_to_idx = {}
        for idx, column_definition in enumerate(items[4].find_data('column_definition')):
            column_name = column_definition.children[0].children[0].lower()
            column_type = ''.join(column_definition.children[1].children).lower()
            column_null = column_definition.children[2] is None

            # Error: When there are duplicates in the column names
            if column_name in column_name_to_idx:
                raise exceptions.DuplicateColumnDefError

            # Error: When the length of `char` type is invalid
            if column_type.startswith('char') and int(column_definition.children[1].children[2]) < 1:
                raise exceptions.CharLengthError

            column_list.append({
                'name': column_name,
                'type': column_type,
                'null': column_null,
                'primary': False,
                'foreign': None
            })

            column_name_to_idx[column_name] = idx

        # Extract the primary key definitions
        primary_key_definition_list = [{
            'column_name_list': [
                column_name.children[0].lower()
                for column_name in primary_key_definition.find_data('column_name')
            ]
        } for primary_key_definition in items[4].find_data('primary_key_definition')]
        if primary_key_definition_list:
            # Error: When there are multiple primary key definitions
            if len(primary_key_definition_list) > 1:
                raise exceptions.DuplicatePrimaryKeyDefError

            primary_key_definition = primary_key_definition_list[0]
            column_name_list = primary_key_definition['column_name_list']

            # Error: When some column does not exist
            non_existing_column_name = next(filter(
                lambda column_name: column_name not in column_name_to_idx,
                column_name_list
            ), None)
            if non_existing_column_name:
                raise exceptions.NonExistingColumnDefError(non_existing_column_name)

            # Error: When there are duplicates in the column names (within the primary key definition)
            if len(set(column_name_list)) < len(column_name_list):
                raise exceptions.EtcError

            for column_name in column_name_list:
                column_list[column_name_to_idx[column_name]].update({'null': False, 'primary': True})

        # Extract the foreign key definitions
        foreign_key_definition_list = [{
            'column_name_list': [
                column_name.children[0].lower()
                for column_name in foreign_key_definition.children[3].find_data('column_name')
            ],
            'ref_table_name': foreign_key_definition.children[6].children[0].lower(),
            'ref_column_name_list': [
                column_name.children[0].lower()
                for column_name in foreign_key_definition.children[8].find_data('column_name')
            ],
        } for foreign_key_definition in items[4].find_data('foreign_key_definition')]
        for foreign_key_definition in foreign_key_definition_list:
            column_name_list = foreign_key_definition['column_name_list']
            ref_table_name = foreign_key_definition['ref_table_name']
            ref_column_name_list = foreign_key_definition['ref_column_name_list']

            # Error: When some column does not exist
            non_existing_column_name = next(filter(
                lambda column_name: column_name not in column_name_to_idx,
                column_name_list
            ), None)
            if non_existing_column_name:
                raise exceptions.NonExistingColumnDefError(non_existing_column_name)

            # Error: When the referred table does not exist (including self-referencing)
            if ref_table_name not in existing_table_name_set:
                raise exceptions.ReferenceTableExistenceError

            referred_table_column_dict = {
                column['name']: column
                for column in self.db_manager.get_table(ref_table_name)['columns']
            }
            referred_table_primary_key_set = {
                column['name']
                for column in referred_table_column_dict.values()
                if column['primary']
            }

            # Error: When some referred column does not exist
            if any(map(
                lambda ref_column_name: ref_column_name not in referred_table_column_dict,
                ref_column_name_list
            )):
                raise exceptions.ReferenceColumnExistenceError

            # Error: When there are duplicates in the column names (within the foreign key definition)
            if (
                len(set(column_name_list)) < len(column_name_list) or
                len(set(ref_column_name_list)) < len(ref_column_name_list)
            ):
                raise exceptions.EtcError

            # Error: When the number of the columns is different from the number of the referred columns
            if len(column_name_list) != len(ref_column_name_list):
                raise exceptions.EtcError

            for column_name, ref_column_name in zip(column_name_list, ref_column_name_list):
                # Error: When the referred column is not primary key
                if ref_column_name not in referred_table_primary_key_set:
                    raise exceptions.ReferenceNonPrimaryKeyError

                column = column_list[column_name_to_idx[column_name]]
                ref_column = referred_table_column_dict.get(ref_column_name)

                # Error: When the column type is different from the referred column type
                if column['type'] != ref_column['type']:
                    raise exceptions.ReferenceTypeError

                # Error: When the column is already defined as foreign key
                if column['foreign']:
                    raise exceptions.EtcError

                column['foreign'] = {'table_name': ref_table_name, 'column_name': ref_column_name}
                referred_table_primary_key_set.remove(ref_column_name)

            # Error: When some of the referred table's primary keys are missing
            if referred_table_primary_key_set:
                raise exceptions.ReferenceNonPrimaryKeyError

        # Create the table in the database
        self.db_manager.set_table(table_name, {'columns': column_list, 'records': []})

        print(f'{PROMPT_TEXT}> \'{table_name}\' table is created')

    def drop_table_query(self, items):
        # Extract the table name
        table_name = items[2].children[0].lower()

        # Error: When the table does not exist
        existing_table_name_set = set(self.db_manager.get_table_names())
        if table_name not in existing_table_name_set:
            raise exceptions.NoSuchTable

        # Error: When a foreign key in another table refers to the table
        for other_table_name in existing_table_name_set - {table_name}:
            if any(map(
                lambda column: column['foreign'] and column['foreign']['table_name'] == table_name,
                self.db_manager.get_table(other_table_name)['columns']
            )):
                raise exceptions.DropReferencedTableError(table_name)

        # Drop the table from the database
        self.db_manager.delete_table(table_name)

        print(f'{PROMPT_TEXT}> \'{table_name}\' table is dropped')

    def explain_query(self, items):
        # Extract the table name
        table_name = items[1].children[0].lower()

        # Error: When the table does not exist
        existing_table_name_set = set(self.db_manager.get_table_names())
        if table_name not in existing_table_name_set:
            raise exceptions.NoSuchTable

        # Load the columns
        column_list = self.db_manager.get_table(table_name)['columns']

        def get_display(column, key):
            """
            Get the display string from a column (name, type, null, or key)
            """

            if key in ('name', 'type'):
                return column[key]
            elif key == 'null':
                return 'Y' if column['null'] else 'N'
            else:
                return '/'.join(filter(None, [
                    'PRI' if column['primary'] else None,
                    'FOR' if column['foreign'] else None
                ]))

        # The information for printing the result
        col_list = ['column_name', 'type', 'null', 'key']
        key_list = ['name', 'type', 'null', 'key']

        # Set the width of each column (based on the longest value for each column)
        width_list = [len(col) + self.WIDTH_PADDING for col in col_list]
        for column in column_list:
            for idx, key in enumerate(key_list):
                width_list[idx] = max(width_list[idx], len(get_display(column, key)) + self.WIDTH_PADDING)

        # Print the result
        dividing_line = '-' * sum(width_list)
        print(dividing_line)
        print(f'table_name [{table_name}]')
        print(''.join([f'{column:<{width_list[idx]}}' for idx, column in enumerate(col_list)]))
        print('\n'.join([
            ''.join([f'{get_display(column, key):<{width_list[idx]}}' for idx, key in enumerate(key_list)])
            for column in column_list
        ]))
        print(dividing_line)

    def describe_query(self, items):
        # The same as `EXPLAIN` query
        self.explain_query(items)

    def desc_query(self, items):
        # The same as `EXPLAIN` query
        self.explain_query(items)

    def insert_query(self, items):
        """
        For project 1-3, here we assume only simple cases as follows.
        - The values in all columns are specified.
        - Each specified values matches the corresponding column type.
        - The value is not null if the corresponding column does not allow null.
        """

        # Extract the table name
        table_name = items[2].children[0].lower()

        # Error: When the table does not exist
        existing_table_name_set = set(self.db_manager.get_table_names())
        if table_name not in existing_table_name_set:
            raise exceptions.NoSuchTable

        # Load the table and its columns
        table = self.db_manager.get_table(table_name)
        column_list = table['columns']

        # The column names that specified what value to insert
        if not items[3]:
            column_name_list = [column['name'] for column in column_list]  # Imply all columns
        else:
            column_name_list = [column_name.children[0].lower() for column_name in items[4].find_data('column_name')]

        # The column values that is specified
        column_value_list = [column_value.children[0] for column_value in items[8].find_data('column_value')]

        # Construct the record to insert
        record = {}
        for column in column_list:
            column_name = column['name']
            column_type = column['type']

            column_value = column_value_list[column_name_list.index(column_name)]

            # Parse the column value
            parsed_type, parsed_value = self.parse_value(column_value)

            # Truncate the `char(n)` value
            if parsed_type == 'char':
                n = int(column_type[5:-1])
                parsed_value = parsed_value[:n]

            record[column_name] = self.serialize_value(parsed_value)

        # Insert the record into the table
        table['records'].append(record)
        self.db_manager.set_table(table_name, table)

        print(f'{PROMPT_TEXT}> The row is inserted')

    def delete_query(self, items):
        pass

    def select_query(self, items):
        """
        For project 1-3, here we assume only `select * from table_name` case.
        (However, I implemented more than the requirement with project 1-3 in mind.)
        """

        # Load the table names
        existing_table_name_set = set(self.db_manager.get_table_names())

        # The set of table names, for detecting conflict in the table names
        table_name_set = set()

        # Prepare the records for each table
        list_of_record_list = []
        column_expr_list = []
        for table_name_as in items[3].find_data('table_expr'):
            # Extract the table name/alias
            table_name = table_name_as.children[0].children[0].lower()
            table_alias = table_name_as.children[2].children[0].lower() if table_name_as.children[2] else None

            # Error: When the table does not exist
            if table_name not in existing_table_name_set:
                raise exceptions.SelectTableExistenceError(table_name)

            # Load the table and its columns/records
            table = self.db_manager.get_table(table_name)
            column_list = table['columns']
            record_list = table['records']

            # Replace the table name with the table alias
            if table_alias:
                table_name = table_alias

            # Error: When the table names conflict
            if table_name in table_name_set:
                raise exceptions.EtcError

            table_name_set.add(table_name)

            # Preprocess the records (for identifying each column and deserializing the values into comparable values)
            preprocessed_record_list = list(map(lambda record: {
                f'{table_name}.{column["name"]}': self.deserialize_value(record[column['name']], column['type'])
                for column in column_list
            }, record_list))
            list_of_record_list.append(preprocessed_record_list)

            column_expr_list.extend([f'{table_name}.{column["name"]}' for column in column_list])

        # Merge all records into a table (Cartesian Product)
        merged_record_list = []
        for comb in itertools.product(*list_of_record_list):
            merged_record = {}
            for record in comb:
                merged_record.update(record)
            merged_record_list.append(merged_record)

        # Select the columns to display
        selected_column_expr_list = column_expr_list  # Select all columns (*)

        def get_display(value):
            """
            Get the display string from a Python value
            """

            if value is None:
                return 'null'
            elif isinstance(value, int):
                return str(value)
            elif isinstance(value, str):
                return value
            else:
                return value.strftime('%Y-%m-%d')

        # Set the width of each column (based on the longest value for each column)
        width_list = [len(column_expr) + self.WIDTH_PADDING for column_expr in selected_column_expr_list]
        for record in merged_record_list:
            for idx, column_expr in enumerate(selected_column_expr_list):
                width_list[idx] = max(width_list[idx], len(get_display(record[column_expr])) + self.WIDTH_PADDING)

        # Print the result
        dividing_line = '+' + '+'.join(['-' * width for width in width_list]) + '+'
        print(dividing_line)
        print('|' + '|'.join([
            f'{f" {column_expr}":<{width_list[idx]}}'
            for idx, column_expr in enumerate(selected_column_expr_list)
        ]) + '|')
        print(dividing_line)
        if merged_record_list:
            print('\n'.join([
                '|' + '|'.join([
                    f'{f" {get_display(record[column_expr])}":<{width_list[idx]}}'
                    for idx, column_expr in enumerate(selected_column_expr_list)
                ]) + '|'
                for record in merged_record_list
            ]))
            print(dividing_line)

    def show_tables_query(self, items):
        # Load the table names
        table_name_list = self.db_manager.get_table_names()

        # Print the result
        dividing_line = '-' * max([*map(lambda table_name: len(table_name), table_name_list), 20])
        print(dividing_line)
        if table_name_list:
            print('\n'.join(table_name_list))
        print(dividing_line)

    def update_query(self, items):
        pass

    def exit_query(self, items):
        # Skip the remaining queries and terminate this process
        exit(0)
