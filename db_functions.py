import sqlite3
import pandas as pd
import numpy as np
from Cryptodome.Cipher import AES
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)


def decrypt_value(nonce, tag, encrypted_text):

    """
    Decripta il valore dell'autobid. Usata all'interno di /conferma_autobid.

    :param nonce: bytes array
    :param tag: bytes array
    :param encrypted_text: bytes array

    :return: str, il valore dell'autobid decriptato

    """

    key = open('key.txt', 'rb').readline()
    cipher = AES.new(key, AES.MODE_EAX, nonce)

    return cipher.decrypt_and_verify(encrypted_text, tag)


def encrypt_value(value):

    """
    Cripta il valore dell'autobid. Utilizzata all'interno di /autobid.

    :param value: str, valore autobid. Ex. "35".

    :return: 3 bytes arrays

    """

    key = open('key.txt', 'rb').readline()
    cipher = AES.new(key, AES.MODE_EAX)
    value2byte = value.encode()
    ciphertext, tag = cipher.encrypt_and_digest(value2byte)

    return cipher.nonce, tag, ciphertext


def db_select(database, table, columns_in=None, columns_out=None,
              where=None, dataframe=False):

    """
    Return content from a specific table of the database.

    :param database: .db object
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

    db, c = start_db(database)

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
            res = [int(i) if type(i) == np.int64 else i for i in res]
            return res
        else:
            res = [tuple(df.iloc[i]) for i in range(len(df))]
            res2 = []
            for i in res:
                temp = []
                for j in i:
                    if type(j) == np.int64:
                        temp.append(int(j))
                    else:
                        temp.append(j)
                res2.append(tuple(temp))
            return res2


# def db_select(table, columns, where=None):
#
#     """
#     Return content from a specific table of the database.
#
#     :param table: str, name of the table
#     :param columns: list, each element of the list is a column of the table.
#     :param where: str, condition
#
#     :return: list of tuples or list of elements
#
#     """
#
#     db, c = start_db()
#
#     cols = ', '.join(columns)
#     if where:
#         query = f'SELECT {cols} FROM {table} WHERE {where}'
#     else:
#         query = f'SELECT {cols} FROM {table}'
#
#     content = list(c.execute(query))
#     db.close()
#
#     if len(columns) == 1 and columns[0] != '*':
#         content = [el[0] for el in content if el[0]]
#
#     return content


def start_db(database):

    db = sqlite3.connect(database)
    c = db.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    return db, c


def empty_table(database, table):

    """
    Delete everything from table.

    :param database: str
    :param table: str

    """

    db, c = start_db(database)

    query = f'DELETE FROM {table}'

    c.execute(query)
    db.commit()
    db.close()


def db_delete(database, table, where):

    """
    Remove entry from database.

    :param database: str
    :param table: str
    :param where: str

    """

    db, c = start_db(database)

    query = f'DELETE FROM {table} WHERE {where}'

    c.execute(query)
    db.commit()
    db.close()


def db_insert(database, table, columns, values):

    """
    Insert a new row in the table.

    :param database: str
    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
    :param values: list, values of the corresponding columns

    """

    db, c = start_db(database)

    cols = ', '.join(columns)
    vals = ', '.join(['?' for _ in values])
    query = f'INSERT INTO {table} ({cols}) VALUES ({vals})'

    c.execute(query, tuple(values))
    db.commit()
    db.close()


def db_update(database, table, columns, values, where):

    """
    Update values in the table.

    :param database: str
    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
    :param values: list, values of the corresponding columns
    :param where: str, condition

    """

    db, c = start_db(database)

    cols = ', '.join([f'{c}=?' for c in columns])
    query = f'UPDATE {table} SET {cols} WHERE {where}'

    c.execute(query, tuple(values))
    db.commit()
    db.close()
