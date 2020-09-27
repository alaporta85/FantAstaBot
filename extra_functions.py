import os
import pandas as pd
import numpy as np
import config as cfg
import db_functions as dbf
from nltk.metrics.distance import jaccard_distance
from nltk.util import ngrams


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
	pls_in_db = dbf.db_select(table='players',
							  columns=['player_name'])

	for x in range(len(players)):
		role, pl, team, price = players.iloc[x].values

		if pl in pls_in_db:
			dbf.db_update(
					table='players',
					columns=['player_team', 'player_price'],
					values=[team[:3].upper(), int(price)],
					where=f'player_name = "{pl}"')
		else:
			dbf.db_insert(
					table='players',
					columns=['player_name', 'player_team',
							 'player_roles', 'player_price', 'player_status'],
					values=[pl, team[:3].upper(), role, int(price), 'FREE'])

	del players


def aggiorna_status_calciatori():

	"""
	Aggiorna lo status di ogni calciatore nella tabella "players" del db.
	Lo status sarà la fantasquadra proprietaria del giocatore mentre ogni
	giocatore svincolato avrà status = FREE.

	"""

	asta = pd.read_excel(os.getcwd() + f'/Asta{cfg.YEAR}.xlsx',
						 sheet_name="Foglio1", usecols=range(0, 32, 4))
	asta = asta.iloc[4:].copy()

	for team in asta.columns:
		pls = asta[team].dropna()
		for pl in pls:
			dbf.db_update(
					table='players',
					columns=['player_status'],
					values=[team],
					where=f'player_name = "{pl.upper()}"')

	dbf.db_update(
			table='players',
			columns=['player_status'],
			values=['FREE'],
			where='player_status IS NULL')


def aggiorna_budgets():

	"""
	Aggiorna lo status di ogni calciatore nella tabella "players" del db.
	Lo status sarà la fantasquadra proprietaria del giocatore mentre ogni
	giocatore svincolato avrà status = FREE.

	"""

	asta = pd.read_excel(os.getcwd() + f'/Asta{cfg.YEAR}.xlsx',
						 sheet_name="Foglio1",
						 usecols=range(0, 32),
	                     nrows=3)

	for i in range(0, 32, 4):
		team = asta.iloc[:, i].name
		budget = int(asta.iloc[2, i+1])
		dbf.db_update(
				table='budgets',
				columns=['budget_value'],
				values=[budget],
				where=f'budget_team = "{team}"')


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

	dbf.empty_table(table='players')

	players = pd.read_excel(os.getcwd() + '/Quotazioni.xlsx',
							sheet_name="Tutti",
							usecols=[1, 2, 3, 4])

	for i in range(len(players)):
		role, name, team, price = players.iloc[i].values
		dbf.db_insert(
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


# 3) Lanciare la funzione:

# quotazioni_iniziali()
# aggiorna_status_calciatori()
# aggiorna_budgets()


# 4) Prima di ogni mercato, scaricare il nuovo Excel con le quotazioni
#    aggiornate, salvarlo con il nome relativo al mercato in questione (Esempio
#    "Quotazioni_PrimoMercato.xlsx") e lanciare la funzione:

# aggiorna_db_con_nuove_quotazioni()


# 5) Utilizzare il bot per il mercato.
