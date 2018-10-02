import sqlite3
import pandas as pd
from Cryptodome.Cipher import AES
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


def decrypt_value(nonce, tag, encrypted_text):

    """
    Decripta il valore dell'autobid.
    Utilizzata all'interno di /conferma_autobid.

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
    Cripta il valore dell'autobid.
    Utilizzata all'interno di /autobid.

    :param value: str, valore autobid. Ex. "35".

    :return: 3 bytes arrays

    """

    bval = value.encode()
    key = open('key.txt', 'rb').readline()
    cipher = AES.new(key, AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(bval)

    return cipher.nonce, tag, ciphertext


def db_insert(table, columns, values):

    """
    Insert a new row in the table assigning the specifies values to the
    specified columns. If last_row=True, return the id of the inserted row.

    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
                    Ex: ['pred_id', 'pred_user', 'pred_quote']. Each column
                    in the list will be loaded.
    :param values: list, values of the corresponding columns

    :return: int if last_row=True else nothing.

    """

    db, c = start_db()

    query = ('''INSERT INTO {} ({}) VALUES ({})'''.format(
            table,
            ', '.join(columns),
            ', '.join(['?' for i in values])))

    c.execute(query, tuple(values))

    db.commit()
    db.close()


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

    query = ('''UPDATE {} SET {} WHERE {}'''.format(
            table,
            ', '.join([i + ' = ?' for i in columns]),
            where))

    c.execute(query, tuple(values))

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
