import sqlite3
import pandas as pd
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


def db_select(table, columns, where=None):

    """
    Return content from a specific table of the database.

    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
    :param where: str, condition

    :return: list of tuples or list of elements

    """

    db, c = start_db()

    cols = ', '.join(columns)
    if where:
        query = f'SELECT {cols} FROM {table} WHERE {where}'
    else:
        query = f'SELECT {cols} FROM {table}'

    content = list(c.execute(query))
    db.close()

    if len(columns) == 1 and columns[0] != '*':
        content = [el[0] for el in content if el[0]]

    return content


def start_db():

    db = sqlite3.connect('fanta_asta_db.db')
    c = db.cursor()
    c.execute("PRAGMA foreign_keys = ON")

    return db, c


def empty_table(table):

    """
    Delete everything from table.

    :param table: str

    """

    db, c = start_db()

    query = f'DELETE FROM {table}'

    c.execute(query)
    db.commit()
    db.close()


def db_delete(table, where):

    """
    Remove entry from database.

    :param table: str
    :param where: str

    """

    db, c = start_db()

    query = f'DELETE FROM {table} WHERE {where}'

    c.execute(query)
    db.commit()
    db.close()


def db_insert(table, columns, values):

    """
    Insert a new row in the table.

    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
    :param values: list, values of the corresponding columns

    """

    db, c = start_db()

    cols = ', '.join(columns)
    vals = ', '.join(['?' for _ in values])
    query = f'INSERT INTO {table} ({cols}) VALUES ({vals})'

    c.execute(query, tuple(values))
    db.commit()
    db.close()


def db_update(table, columns, values, where):

    """
    Update values in the table.

    :param table: str, name of the table
    :param columns: list, each element of the list is a column of the table.
    :param values: list, values of the corresponding columns
    :param where: str, condition

    """

    db, c = start_db()

    cols = ', '.join([f'{c}=?' for c in columns])
    query = f'UPDATE {table} SET {cols} WHERE {where}'

    c.execute(query, tuple(values))
    db.commit()
    db.close()
