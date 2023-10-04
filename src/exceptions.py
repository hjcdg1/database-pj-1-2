class DuplicateColumnDefError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: column definition is duplicated')


class DuplicatePrimaryKeyDefError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: primary key definition is duplicated')


class ReferenceTypeError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: foreign key references wrong type')


class ReferenceNonPrimaryKeyError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: foreign key references non primary key column')


class ReferenceColumnExistenceError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: foreign key references non existing column')


class ReferenceTableExistenceError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: foreign key references non existing table')


class NonExistingColumnDefError(Exception):
    def __init__(self, column_name):
        super().__init__(f'Create table has failed: \'{column_name}\' does not exist in column definition')


class TableExistenceError(Exception):
    def __init__(self):
        super().__init__('Create table has failed: table with the same name already exists')


class CharLengthError(Exception):
    def __init__(self):
        super().__init__('Char length should be over 0')


class NoSuchTable(Exception):
    def __init__(self):
        super().__init__('No such table')


class DropReferencedTableError(Exception):
    def __init__(self, table_name):
        super().__init__(f'Drop table has failed: \'{table_name}\' is referenced by other table')


class SelectTableExistenceError(Exception):
    def __init__(self, table_name):
        super().__init__(f'Selection has failed: \'{table_name}\' does not exist')


class EtcError(Exception):
    def __init__(self):
        super().__init__('Etc error')
