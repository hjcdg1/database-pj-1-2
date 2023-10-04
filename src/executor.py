from lark import Transformer

from src.database import DatabaseManager

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
    def __init__(self, database):
        super().__init__()
        self.db_manager = DatabaseManager(database)

    def execute(self, tree):
        """
        Rename `transform` method for improving readability
        """

        self.transform(tree)

    def create_table_query(self, items):
        pass

    def drop_table_query(self, items):
        pass

    def explain_query(self, items):
        pass

    def describe_query(self, items):
        pass

    def desc_query(self, items):
        pass

    def insert_query(self, items):
        pass

    def delete_query(self, items):
        pass

    def select_query(self, items):
        pass

    def show_tables_query(self, items):
        pass

    def update_query(self, items):
        pass

    def exit_query(self, items):
        # Skip the remaining queries and terminate this process
        exit(0)
