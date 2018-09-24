import sqlite3
import datetime
import pandas as pd
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


def db_delete(table, where):

    """
    Delete row from table.

    :param table: str

    :param where: str


    :return: Nothing
    """

    db, c = start_db()

    c.execute('''DELETE FROM {} WHERE {}'''.format(table, where))

    db.commit()
    db.close()


def db_insert(table, columns, values, last_row=False):

    """
    Insert a new row in the table assigning the specifies values to the
    specified columns. If last_row=True, return the id of the inserted row.

    :param table: str, name of the table

    :param columns: list, each element of the list is a column of the table.
                    Ex: ['pred_id', 'pred_user', 'pred_quote']. Each column
                    in the list will be loaded.

    :param values: list, values of the corresponding columns

    :param last_row: bool


    :return: int if last_row=True else nothing.
    """

    db, c = start_db()

    placeholders = ['"{}"' if (type(v) == str or type(v) == datetime.datetime)
                    else '{}' for v in values]
    vals = [el[0].format(el[1]) for el in zip(placeholders, values)]

    c.execute('''INSERT INTO {} ({}) VALUES ({})'''.
              format(table, ','.join(columns), ','.join(vals)))
    last_id = c.lastrowid
    db.commit()
    db.close()

    if last_row:
        return last_id


def db_select(table, columns_in=None, columns_out=None,
              where=None, dataframe=False):

    """
    Return content from a specific table of the database.

    :param table: str, name of the table

    :param columns_in: list, each element of the list is a column of the table.
                       Ex: ['pred_id', 'pred_user', 'pred_quote']. Each column
                       in the list will be loaded.

    :param columns_out: list, each element of the list is a column of the
                        table. Ex: ['pred_label']. Each column in the list will
                        not be loaded.

    :param where: str, condition. Ex: 'pred_label == WINNING'

    :param dataframe: bool


    :return: Dataframe if dataframe=True else list of tuples.
    """

    db, c = start_db()

    if where:
        cursor = c.execute('''SELECT * FROM {} WHERE {}'''.format(table,
                                                                  where))
    else:
        cursor = c.execute('''SELECT * FROM {}'''.format(table))

    cols = [el[0] for el in cursor.description]

    df = pd.DataFrame(list(cursor), columns=cols)
    db.close()

    if not len(df):
        return []

    if columns_in:
        cols = [el for el in cols if el in columns_in]
        df = df[cols]

    elif columns_out:
        cols = [el for el in cols if el not in columns_out]
        df = df[cols]

    if dataframe:
        return df
    else:
        if len(cols) == 1:
            res = [df.loc[i, cols[0]] for i in range(len(df))]
            res = sorted(set(res), key=lambda x: res.index(x))
            return res
        else:
            res = [tuple(df.iloc[i]) for i in range(len(df))]
            return res


def db_update(table, columns, values, where):

    """
    Update values in the table assigning the specifies values to the
    specified columns.

    :param table: str, name of the table

    :param columns: list, each element of the list is a column of the table.
                    Ex: ['pred_id', 'pred_user', 'pred_quote']. Each column
                    in the list will be loaded.

    :param values: list, values of the corresponding columns

    :param where: str, condition


    :return: Nothing
    """

    db, c = start_db()

    placeholders = ['"{}"' if (type(v) == str or type(v) == datetime.datetime)
                    else '{}' for v in values]
    vals = [el[0].format(el[1]) for el in zip(placeholders, values)]
    vals = ['{}={}'.format(el[0], el[1]) for el in zip(columns, vals)]

    c.execute('''UPDATE {} SET {} WHERE {}'''.format(table, ','.join(vals),
                                                     where))

    db.commit()
    db.close()


def empty_table(table):

    """
    Called inside fill_db_with_quotes.

    :param table: str


    :return: Nothing
    """

    db, c = start_db()

    c.execute('''DELETE FROM {}'''.format(table))

    db.commit()
    db.close()


def start_db():

    db = sqlite3.connect('fanta_asta_db.db')
    c = db.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    return db, c
