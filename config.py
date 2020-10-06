YEAR = '2020-2021'

with open('token.txt', 'r') as f:
	TOKEN = f.readline()

# True durante il debugging, reindirizza a Testazza tutti i messaggi
# solitamente mandati al gruppo
BLOCK = False
FANTA_ID = -318148079
POLPS_ID = 67507055

# Tempo in secondi per considerare vinta un'asta
TIME_WINDOW1 = 86400
# Tempo in secondi per ufficializzare
TIME_WINDOW2 = 86400

SEPAR = '\n\n' + '_' * 25 + '\n\n\n'
