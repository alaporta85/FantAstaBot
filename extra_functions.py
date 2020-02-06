import os
import pandas as pd
import numpy as np
import db_functions as dbf
from pandas import ExcelWriter
from nltk.metrics.distance import jaccard_distance
from nltk.util import ngrams


anno = '2019-2020'
dbase = 'fanta_asta_db.db'


def aggiorna_db_con_nuove_quotazioni():

	"""
	Aggiorna tutte le quotazioni dei calciatori prima di ogni mercato.
	Gestisce anche i trasferimenti interni alla Serie A aggiornando la
	squadra di appartenenza e l'arrivo di nuovi calciatori.

	"""

	mercati = ['PrimoMercato', 'SecondoMercato', 'TerzoMercato']

	last = ''

	for i in mercati:
		name = os.getcwd() + '/Quotazioni_' + i + '.xlsx'
		if os.path.isfile(name):
			last = name

	players = pd.read_excel(last, sheet_name="Tutti", usecols=[1, 2, 3, 4])
	pls_in_db = dbf.db_select(database=dbase,
	                          table='players',
							  columns=['player_name'])

	for x in range(len(players)):
		role, pl, team, price = players.iloc[x].values

		if pl in pls_in_db:
			dbf.db_update(
					database=dbase,
					table='players',
					columns=['player_team', 'player_price'],
					values=[team[:3].upper(), int(price)],
					where='player_name = "{}"'.format(pl))

			# dbf.db_update(
			# 		database=dbase,
			# 		table='stats',
			# 		columns=['team', 'price'],
			# 		values=[team[:3].upper(), int(price)],
			# 		where='name = "{}"'.format(pl))
		else:
			dbf.db_insert(
					database=dbase,
					table='players',
					columns=['player_name', 'player_team',
							 'player_roles', 'player_price', 'player_status'],
					values=[pl, team[:3].upper(), role, int(price), 'FREE'])

			# dbf.db_insert(
			# 		database=dbase,
			# 		table='stats',
			# 		columns=['name', 'team', 'roles', 'status', 'mv', 'mfv',
			# 		         'regular', 'going_in', 'going_out', 'price'],
			# 		values=[pl, team[:3].upper(), role, 'FREE', 0, 0,
			# 		        0, 0, 0, int(price)])

	del players


def aggiorna_status_calciatori():

	"""
	Aggiorna lo status di ogni calciatore nella tabella "players" del db.
	Lo status sarà la fantasquadra proprietaria del giocatore mentre ogni
	giocatore svincolato avrà status = FREE.

	"""

	asta = pd.read_excel(os.getcwd() + '/Asta{}.xlsx'.format(anno),
						 sheet_name="Foglio1-1", usecols=range(0, 24, 3))

	for team in asta.columns:
		pls = asta[team].dropna()
		for pl in pls:
			dbf.db_update(
					database=dbase,
					table='players',
					columns=['player_status'],
					values=[team], where='player_name = "{}"'.format(pl))

	dbf.db_update(
			database=dbase,
			table='players',
			columns=['player_status'],
			values=['FREE'], where='player_status IS NULL')


def correggi_file_asta():

	"""
	Crea una copia del file originale contenente le rose definite il giorno
	dell'asta ma con i nomi dei calciatori corretti secondo il formato di
	Fantagazzetta.

	"""

	asta = pd.read_excel(os.getcwd() + '/Asta{}.xlsx'.format(anno),
						 header=0, sheet_name="Foglio1")
	players = dbf.db_select(
			database=dbase,
			table='players',
			columns=['player_name', 'player_team'])

	# TODO make df from players

	for i in range(0, len(asta.columns), 3):
		temp_pl = asta[asta.columns[i:i+3]].dropna()
		for j in range(len(temp_pl)):
			pl, tm = temp_pl.loc[j, temp_pl.columns[0:2]]
			flt_df = players[players['player_team'] == tm.upper()]
			names = flt_df['player_name'].values
			correct_pl = jaccard_result(pl, names, 3)
			asta.loc[j, [asta.columns[i],
						 asta.columns[i+1]]] = correct_pl, tm.upper()

	writer = ExcelWriter('Asta{}_2.xlsx'.format(anno), engine='openpyxl')
	asta.to_excel(writer, sheet_name='Foglio1')
	writer.save()
	writer.close()


def jaccard_result(in_opt, all_opt, ngrm):

	"""
	Fix user input.

	:param in_opt: str
	:param all_opt: list
	:param ngrm: int, ngrams length

	:return jac_res: str

	"""

	in_opt = in_opt.lower().replace(' ', '')
	n_in = set(ngrams(in_opt, ngrm))

	out_opts = [pl.lower().replace(' ', '') for pl in all_opt]
	n_outs = [set(ngrams(pl, ngrm)) for pl in out_opts]

	distances = [jaccard_distance(n_in, n_out) for n_out in n_outs]

	if len(set(distances)) == 1 and distances[0] == 1:
		return jaccard_result(in_opt, all_opt, ngrm-1) if ngrm > 2 else False
	else:
		return all_opt[np.argmin(distances)]


def quotazioni_iniziali():

	"""
	Dopo averla svuotata, riempie la tabella "players" del db con tutti i dati
	relativi a ciascun giocatore ad inizio campionato.

	"""

	dbf.empty_table(database=dbase, table='players')

	players = pd.read_excel(os.getcwd() + '/Quotazioni.xlsx',
							sheet_name="Tutti", usecols=[1, 2, 3, 4])

	for i in range(len(players)):
		role, name, team, price = players.iloc[i].values
		dbf.db_insert(
				database=dbase,
				table='players',
				columns=['player_name', 'player_team',
						 'player_roles', 'player_price'],
				values=[name, team[:3].upper(), role, int(price)])

	del players


# 1) Scaricare le quotazioni di tutti i giocatori dal sito di Fantagazzetta e
#    salvarle all'interno della cartella del bot con il nome "Quotazioni.xlsx".


# 2) Ad asta conclusa, salvare il file con tutte le rose all'interno della
#    cartella del bot con il nome "Asta2018-2019.xlsx". Aggiornare inoltre il
#    db con i corretti nomi delle 8 squadre partecipanti ed accertarsi siano
#    uguali a quelli presenti nel file "Asta2018-2019.xlsx". Aggiornare anche i
#    budgets post-asta di ciascuna squadra all'interno del db.


# 3) Lanciare le funzioni:

# quotazioni_iniziali()
# correggi_file_asta()


# 4) A questo punto nella cartella ci sarà un nuovo file chiamato
#    "Asta2018-2019_2.xlsx". Copiare la tabella in esso contenuta ed incollarla
#    in un secondo Foglio di calcolo appositamente creato nel file originale
#    "Asta2018-2019.xlsx". Il nuovo Foglio di calcolo dovrà chiamarsi
#    "Foglio1-1".


# 5) Lanciare la funzione:

# aggiorna_status_calciatori()


# 6) Prima di ogni mercato, scaricare il nuovo Excel con le quotazioni
#    aggiornate, salvarlo con il nome relativo al mercato in questione (Esempio
#    "Quotazioni_PrimoMercato.xlsx") e lanciare la funzione:

# aggiorna_db_con_nuove_quotazioni()


# 7) Utilizzare il bot per il mercato.
