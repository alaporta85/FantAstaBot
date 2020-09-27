from datetime import datetime, timedelta
import config as cfg
import db_functions as dbf
import extra_functions as ef


def aggiorna_offerte_chiuse(dt_now, return_offers=False):

	"""
	Confronta i tempi trascorsi da ogni offerta e chiude quelle che hanno già
	raggiunto o superato le 24 ore necessarie.
	Utilizzata all'interno di confermo_autobid(), confermo_offerta(),
	crea_riepilogo(), offro() e pago().

	:param dt_now: datetime, data e ora attuale
	:param return_offers: bool

	:return offers_win: list, contiene le offerte ancora aperte
	:return offers_no: list, contiene le offerte chiuse e non ufficializzate

	"""

	offers_win = dbf.db_select(
			table='offers',
			columns=['offer_id', 'offer_user', 'offer_player',
			         'offer_price', 'offer_dt'],
			where='offer_status = "Winning"')

	offers_no = dbf.db_select(
			table='offers',
			columns=['offer_id', 'offer_user', 'offer_player',
			         'offer_price', 'offer_dt'],
			where='offer_status = "Not Official"')

	# Se tra le offerte aperte ce n'è qualcuna per la quale sono già scadute
	# le 24 ore allora il suo status viene modificato a 'Not Official' ed
	# elimina eventuali autobids attivi per quel calciatore
	for of_id, tm, pl, pr, dt in offers_win:
		dt2 = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
		diff = dt_now - dt2
		if diff.total_seconds() > cfg.TIME_WINDOW1:
			offers_no.append((of_id, tm, pl, pr, dt))
			dbf.db_update(table='offers',
						  columns=['offer_status'],
						  values=['Not Official'],
						  where=f'offer_id = {of_id}')
			dbf.db_update(table='players',
						  columns=['player_status'],
						  values=[tm],
						  where=f'player_name = "{pl}"')
			dbf.db_delete(table='autobids',
			              where=f'autobid_player = "{pl}"')

	if return_offers:

		# Ridefinisco le due liste trasformando le stringhe in oggetti datetime
		offers_win = [(el[0], el[1], el[2], el[3],
		               datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
		              offers_win if el not in offers_no]

		offers_no = [(el[0], el[1], el[2], el[3],
		              datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
		             offers_no]

		return offers_win, offers_no


def autorilancio(user, player_name):

	"""
	Controlla che l'user non stia effettuando un autorilancio.

	:param user: str, fantasquadra
	:param player_name: str, nome calciatore

	:return: bool, True se autorilancio altrimenti False

	"""

	offer = dbf.db_select(
			table='offers',
			columns=['offer_id'],
			where=(f'offer_user = "{user}" AND ' +
			       f'offer_player = "{player_name}" AND ' +
			       'offer_status = "Winning"'))

	if offer:
		return True
	else:
		return False


def check_autobid_format(args):

	"""
	Controlla che il formato del comando sia inviato correttamente.
	Utilizzata all'interno di autobid().

	:param args: list, input dell'user

	:return: str o tuple a seconda dei casi

	"""

	message = 'Inserire i dati. Ex: /autobid petagna, 30'
	args = ''.join(args).split(',')

	if not args or len(args) != 2:
		return message

	try:
		int(args[0])
		ab, pl = args
	except ValueError:
		pl, ab = args
		try:
			int(ab)
		except ValueError:
			return "Manca l'autobid."

	# Cerco nel db il calciatore corrispondente
	jpl = ef.jaccard_result(pl, dbf.db_select(
			table='players',
			columns=['player_name'],
			where='player_status = "FREE"'), 3)
	if not jpl:
		return ('Giocatore non trovato. Controllare che sia ' +
				'scritto correttamente e svincolato.')
	else:
		return jpl, ab


def check_autobid_value(user, player, new_id, new_ab):

	"""
	Esamina tutti i possibili casi ed agisce di conseguenza.

	:param user: str, fantasquadra
	:param player: str, calciatore
	:param new_id: int, id dell'autobid nel db
	:param new_ab: int, valore dell'autobid

	:return: tuple, bool o str

	"""

	# Controllo se c'è già un'asta in corso per il calciatore
	try:
		last_id, last_user, last_offer = dbf.db_select(
				table='offers',
				columns=['offer_id', 'offer_user', 'offer_price'],
				where=(f'offer_player = "{player}" AND ' +
				       'offer_status = "Winning"'))[0]

	except IndexError:
		last_id = 0
		last_user = None
		last_offer = 0

	# Se non c'è, gestisco la situazione in modo da presentare automaticamente
	# un'offerta a prezzo base oppure segnalare all'utente l'assenza di un'asta
	# attiva
	if not last_offer:
		private, group = prezzo_base_automatico(user, new_id, player, new_ab,
		                                        active=True)
		return private, group

	# Se invece c'è allora ne confronto il valore con l'autobid che si sta
	# provando ad impostare. Se l'autobid è inferiore o uguale, lo elimino dal
	# db e lo segnalo all'user
	if new_ab <= last_offer:
		dbf.db_delete(
				table='autobids',
				where=f'autobid_id = {new_id}')

		return ("Valore autobid troppo basso. Impostare un valore superiore" +
		        " all'attuale offerta vincente."), None

	# Se è superiore allora devo controllare che l'user dell'ultima offerta non
	# abbia impostato anche lui un autobid
	else:
		old_ab = dbf.db_select(
				table='autobids',
				columns=['autobid_id', 'autobid_nonce',
				         'autobid_tag', 'autobid_value'],
				where=(f'autobid_player = "{player}" AND ' +
				       'autobid_status = "Confirmed"'))

		# Caso 1: non c'è autobid ed il detentore dell'offerta è un avversario.
		# In questo caso l'avversario perde l'offerta a favore del nuovo user.
		# Il valore della nuova offerta sarà automaticamente uguale ad 1
		# fantamilione in più rispetto alla precedente
		if not old_ab and user != last_user:

			dbf.db_update(
					table='offers',
					columns=['offer_status'],
					values=['Lost'],
					where=f'offer_id = {last_id}')

			dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

			pl_id = dbf.db_select(
						table='players',
					columns=['player_id'],
					where=f'player_name = "{player}"')[0]

			dbf.db_insert(
					table='offers',
					columns=['offer_user', 'offer_player', 'offer_player_id',
					         'offer_price', 'offer_dt', 'offer_status'],
					values=[user, player, pl_id, last_offer + 1, dt, 'Winning'])

			# Cancello l'autobid nel caso venga raggiunto il suo valore
			if new_ab == last_offer + 1:
				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')

				private = ('Hai dovuto utilizzare tutto il tuo autobid. ' +
				           'Reimposta un valore più alto nel caso volessi ' +
				           'continuare ad usarlo.' + cfg.SEPAR +
				           crea_riepilogo_autobid(user))
			else:
				dbf.db_update(
						table='autobids',
						columns=['autobid_status'],
						values=['Confirmed'],
						where=f'autobid_id = {new_id}')

				private = ('Offerta aggiornata ed autobid impostato ' +
				           'correttamente.' + cfg.SEPAR +
				           crea_riepilogo_autobid(user))

			group = (f'<i>{user}</i> rilancia per <b>{player}</b>.' +
			         cfg.SEPAR + crea_riepilogo(dt))

			return private, group

		# Caso 2: non c'è autobid ed il detentore dell'offerta è lo stesso user.
		# In questo caso viene semplicemente impostato l'autobid
		elif not old_ab and user == last_user:

			dbf.db_update(
					table='autobids',
					columns=['autobid_status'],
					values=['Confirmed'],
					where=f'autobid_id = {new_id}')

			return ('Autobid impostato correttamente.' + cfg.SEPAR +
				    crea_riepilogo_autobid(user)), None

		# Se c'è già un autobid si aprono altri possibili casi
		else:
			old_id, last_nonce, last_tag, last_value = old_ab[0]
			old_ab = int(dbf.decrypt_value(last_nonce, last_tag, last_value).
			             decode())

			# Caso 3: il nuovo autobid supera il vecchio ed il detentore
			# dell'offerta è un avversario. Simile al Caso 1.
			# Il valore della nuova offerta sarà automaticamente uguale ad 1
			# fantamilione in più rispetto al precedente autobid
			if new_ab > old_ab and user != last_user:

				dbf.db_update(
						table='offers',
						columns=['offer_status'],
						values=['Lost'],
						where=f'offer_id = {last_id}')

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {old_id}')

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				pl_id = dbf.db_select(
						table='players',
						columns=['player_id'],
						where=f'player_name = "{player}"')[0]

				dbf.db_insert(
						table='offers',
						columns=['offer_user', 'offer_player',
						         'offer_player_id',
						         'offer_price', 'offer_dt',
						         'offer_status'],
						values=[user, player, pl_id, old_ab + 1, dt,
						        'Winning'])

				if new_ab == old_ab + 1:
					dbf.db_delete(
							table='autobids',
							where=f'autobid_id = {new_id}')

					private = ('Hai dovuto utilizzare tutto il tuo autobid. ' +
					           'Reimposta un valore più alto nel caso ' +
					           'volessi continuare ad usarlo.' + cfg.SEPAR +
					           crea_riepilogo_autobid(user))
				else:
					dbf.db_update(
							table='autobids',
							columns=['autobid_status'],
							values=['Confirmed'],
							where=f'autobid_id = {new_id}')

					private = ('Offerta aggiornata ed autobid impostato ' +
					           'correttamente.' + cfg.SEPAR +
					           crea_riepilogo_autobid(user))

				group = (f'<i>{user}</i> rilancia ' +
						 f'per <b>{player}</b>.' + cfg.SEPAR + crea_riepilogo(dt))

				return private, group

			# Caso 4: il nuovo autobid supera il vecchio ed il detentore
			# dell'offerta è lo stesso user. Viene aggiornato l'autobid
			# precedente al nuovo valore più alto
			elif new_ab > old_ab and user == last_user:

				nonce, tag, value = dbf.encrypt_value(str(new_ab))
				dbf.db_update(
						table='autobids',
						columns=['autobid_nonce', 'autobid_tag',
						         'autobid_value'],
						values=[nonce, tag, value],
						where=f'autobid_id = {old_id}')

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')

				return (f'Hai aumentato il tuo autobid per {player} ' +
				        f'da {old_ab} a {new_ab}.' + cfg.SEPAR +
				        crea_riepilogo_autobid(user)), None

			# Caso 5: il nuovo autobid non supera il vecchio ed il detentore
			# dell'offerta è un avversario. Il nuovo autobid non viene
			# confermato e l'offerta del detentore viene aggiornata ad un
			# valore pari all'autobid tentato dall'user più 1 fantamilione
			elif new_ab < old_ab and user != last_user:

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')

				dbf.db_update(
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[new_ab + 1, dt],
						where=f'offer_id = {last_id}')

				if old_ab == new_ab + 1:
					dbf.db_delete(
							table='autobids',
							where=f'autobid_id = {old_id}')

				private = 'Autobid troppo basso.'
				group = (f'<i>{user}</i> ha tentato un rilancio' +
						 f' per <b>{player}</b>.' + cfg.SEPAR + crea_riepilogo(dt))

				return private, group

			# Caso 6: il nuovo autobid non supera il vecchio ed il detentore
			# dell'offerta è lo stesso user. Viene aggiornato l'autobid
			# precedente al nuovo valore più basso
			elif new_ab < old_ab and user == last_user:

				nonce, tag, value = dbf.encrypt_value(str(new_ab))
				dbf.db_update(
						table='autobids',
						columns=['autobid_nonce', 'autobid_tag',
						         'autobid_value'],
						values=[nonce, tag, value],
						where=f'autobid_id = {old_id}')

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')

				return (f'Hai diminuito il tuo autobid per {player} ' +
				        f'da {old_ab} a {new_ab}.' + cfg.SEPAR +
				        crea_riepilogo_autobid(user)), None

			# Caso 7: il nuovo autobid è uguale al vecchio ed il detentore
			# dell'offerta è un avversario. Viene convalidato quello del
			# detentore per averlo impostato in anticipo
			elif new_ab == old_ab and user != last_user:

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				sex = dbf.db_select(
						table='teams',
						columns=['team_sex'],
						where=f'team_name = "{last_user}"')[0]

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')

				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {old_id}')

				dbf.db_update(
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[new_ab, dt],
						where=f'offer_id = {last_id}')

				private = (f"Autobid uguale a quello di {last_user}." +
				           " Ha la precedenza " + sex + " perché l'ha " +
				           "impostato prima.")
				group = (f'<i>{user}</i> ha tentato un rilancio' +
						 f' per <b>{player}</b>.' + cfg.SEPAR + crea_riepilogo(dt))

				return private, group

			# Caso 8: il nuovo autobid è uguale al vecchio ed il detentore
			# dell'offerta è lo stesso user.
			elif new_ab == old_ab and user == last_user:
				dbf.db_delete(
						table='autobids',
						where=f'autobid_id = {new_id}')
				return 'Hai già impostato questo valore di autobid.', None


def check_offer_format(args):

	"""
	Controlla che il formato dell'offerta sia corretto.
	Ritorna un messaggio esplicativo in caso di formato errato.
	Utilizzata all'interno di offro().

	:param args: list, input dell'utente

	:return offer: int, soldi offerti
	:return pl: str, nome del giocatore
	:return team: str, nome della squadra alla quale appartiene il giocatore

	"""

	message = 'Inserire i dati. Es: /offro 5, padoin'
	args = ''.join(args).split(',')

	if not args or len(args) != 2:
		return message

	try:
		int(args[0])
		offer, pl = args
	except ValueError:
		pl, offer = args
		try:
			int(offer)
		except ValueError:
			return "Manca l'offerta."

	# Cerco il calciatore corrispondente all'input dell'user ed aggiorno il db
	jpl = ef.jaccard_result(pl, dbf.db_select(
			table='players',
			columns=['player_name'],
			where='player_status = "FREE"'), 3)
	if not jpl:
		return ('Giocatore non trovato. Controllare che sia ' +
				'scritto correttamente e svincolato.')

	return offer, jpl


def check_offer_value(user, offer_id, player, dt):

	"""
	Controlla che il valore dell'offerta sia valido. Nell'ordine:

		- In caso di prima offerta, se il valore offerto è sufficiente
		- In caso di rilancio, se l'offerta supera quella già presente
		- Nel caso la superi, se l'offerta supera un possibile autobid

	Utilizzata all'interno di confermo_offerta().

	:param user: str, fantasquadra
	:param offer_id: int, id dell'offerta
	:param player: str, nome del giocatore
	:param dt: str, data ed ora attuali

	:return : str o tuple, messaggi in chat

	"""

	offer = dbf.db_select(
			table='offers',
			columns=['offer_price'],
			where=f'offer_id = {offer_id}')[0]

	# Prendo dal db i dettagli dell'ultima offerta valida per questo
	# calciatore, qualora ci sia
	try:
		last_id, last_user, last_offer = dbf.db_select(
				table='offers',
				columns=['offer_id', 'offer_user', 'offer_price'],
				where=(f'offer_player = "{player}" AND ' +
				       'offer_status = "Winning"'))[0]
	except IndexError:
		last_id = 0
		last_user = None
		last_offer = 0

	# Se si tratta di prima offerta, ne confronto il valore con il prezzo base
	# del calciatore ed aggiorno il db
	if not last_offer:
		price = dbf.db_select(
				table='players',
				columns=['player_price'],
				where=f'player_name = "{player}"')[0]
		if offer < price:
			dbf.db_delete(
					table='offers',
			        where=f'offer_id = {offer_id}')

			return f'Offerta troppo bassa. Quotazione: {price}'
		else:

			dbf.db_update(
					table='offers',
					columns=['offer_dt', 'offer_status'],
					values=[dt, 'Winning'],
					where=f'offer_id = {offer_id}')

			private = 'Offerta aggiornata correttamente.'

			group = (f'<i>{user}</i> offre per <b>{player}</b>.' +
			         cfg.SEPAR + crea_riepilogo(dt))

			return private, group

	# Se si tratta di rilancio, controllo che l'offerta superi quella già
	# esistente
	else:
		if offer <= last_offer:
			dbf.db_delete(
					table='offers',
			        where=f'offer_id = {offer_id}')

			return ('Offerta troppo bassa. ' +
			        f'Ultimo rilancio: {last_offer}, {last_user}')
		else:
			# Se la supera, resta da confrontarla con un eventuale autobid.
			# Quindi seleziono l'autobid già impostato dall'altro user oppure,
			# qualora non esista, assegno valore nullo ad alcune variabili in
			# modo da gestire il codice successivo
			try:
				iid, ab_user, nonce, tag, encr_value = dbf.db_select(
						table='autobids',
						columns=['autobid_id', 'autobid_user', 'autobid_nonce',
						         'autobid_tag', 'autobid_value'],
						where=f'autobid_player = "{player}"')[0]
				last_ab = int(dbf.decrypt_value(nonce, tag, encr_value).
				              decode())
			except IndexError:
				iid = 0
				ab_user = None
				last_ab = 0

			# Se l'offerta è inferiore all'autobid di un altro user: cancello
			# l'offerta dal db, aggiorno il valore dell'offerta dell'altro
			# utente e, qualora questo nuovo valore raggiunga il suo limite
			# di autobid, elimino tale autobid dal db
			if offer < last_ab:
				dbf.db_delete(
						table='offers',
				        where=f'offer_id = {offer_id}')
				dbf.db_update(
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[offer + 1, dt],
						where=f'offer_id = {last_id}')
				if offer + 1 == last_ab:
					dbf.db_delete(
							table='autobids',
					        where=f'autobid_id = {iid}')

				private = ("Offerta troppo bassa. Non hai superato" +
				           f" l'autobid di {ab_user}.")

				group = (f'<i>{user}</i> ha tentato un rilancio ' +
				         f'per <b>{player}</b>.' +
				         cfg.SEPAR + crea_riepilogo(dt))

				return private, group

			# Se invece l'offerta supera l'ultimo autobid allora cancello tale
			# autobid dal db ed aggiorno tutti gli altri parametri
			else:

				dbf.db_delete(
						table='autobids',
				        where=f'autobid_id = {iid}')

				dbf.db_update(
						table='offers',
						columns=['offer_dt', 'offer_status'],
						values=[dt, 'Winning'],
						where=f'offer_id = {offer_id}')

				dbf.db_update(
						table='offers',
						columns=['offer_status'],
						values=['Lost'],
						where=f'offer_id = {last_id}')

				private = 'Offerta aggiornata correttamente.'

				group = (f'<i>{user}</i> ha rilanciato per <b>{player}</b>.' +
				         cfg.SEPAR + crea_riepilogo(dt))

				return private, group


def check_pago_format(args):

	"""
	Controlla il formato dell'input di pagamento e ritorna un messaggio
	esplicativo in caso di errore. Si assicura inoltre che l'offerta sia
	pagabile, ovvero che il giocatore in questione sia effettivamente dell'user
	e che siano trascorse le 24 ore necessarie.
	Utilizzata all'interno di pago().

	:param args: list, il pagamento dell'user

	:return: tuple, l'acquisto e il pagamento

	"""

	message = 'Formato errato. Es: /pago higuain, padoin, khedira, 18.'

	if not args:
		return 'Inserire i dati. Es: /pago higuain, padoin, khedira, 18.'

	args = ''.join(args).split(',')

	if len(args) < 2:
		return message

	try:
		int(args[0])
		return message
	except ValueError:
		pass

	return args[0], args[1:]


def crea_riepilogo(dt_now):

	"""
	Mette insieme i vari messaggi di riepilogo delle offerte:

		- Aperte
		- Concluse ma non ufficializzate
		- Ufficializzate

	Utilizzata dentro confermo_offerta() e riepilogo().

	:param dt_now: str, data e ora da trasformare in datetime

	:return: messaggio in chat

	"""

	dt_now = datetime.strptime(dt_now, '%Y-%m-%d %H:%M:%S')

	message1 = 'Aste APERTE, Tempo Rimanente:\n'
	message2 = 'Aste CONCLUSE, NON Ufficializzate:\n'

	offers_win, offers_no = aggiorna_offerte_chiuse(dt_now, return_offers=True)

	message1 = message_with_offers(offers_win, cfg.TIME_WINDOW1, dt_now, message1)
	message2 = message_with_offers(offers_no, cfg.TIME_WINDOW1 + cfg.TIME_WINDOW2,
	                               dt_now, message2)

	message = message1 + '\n\n\n\n' + message2

	return message


def crea_riepilogo_autobid(user):

	"""
	Crea il messaggio di riepilogo degli autobid attivi dell'user.
	Utilizzata dentro riepilogo_autobid().

	:param user: str, fantasquadra

	:return: str, messaggio in chat

	"""

	autobids = dbf.db_select(
			table='autobids',
			columns=['autobid_player', 'autobid_nonce',
			         'autobid_tag', 'autobid_value'],
			where=f'autobid_user = "{user}" AND autobid_status = "Confirmed"')
	if not autobids:
		return 'Nessun autobid attivo.'

	message = 'I tuoi autobid attivi sono:\n\n'
	for pl, nonce, tag, encr_ab in autobids:
		decr_ab = int(dbf.decrypt_value(nonce, tag, encr_ab).decode())
		message += f'\t\t\t\t<b>{pl}</b>: {decr_ab}\n'

	return message


def message_with_offers(list_of_offers, shift, dt_now, msg):

	"""
	Crea il messaggio di riepilogo delle offerte.
	Utilizzata dentro crea_riepilogo().

	:param list_of_offers: list, ogni tuple è un'offerta
	:param shift: int, per calcolare lo shift in secondi e il tempo rimanente
	:param dt_now: datetime, data e ora attuali
	:param msg: str, messaggio da completare

	:return msg: str, messaggio finale

	"""

	for _, tm, pl, pr, dt in list_of_offers:
		team, roles = dbf.db_select(
				table='players',
				columns=['player_team', 'player_roles'],
				where=f'player_name = "{pl}"')[0]
		dt_plus = dt + timedelta(seconds=shift)
		diff = (dt_plus - dt_now).total_seconds()
		if diff < 0:
			diff = abs(diff)
			hh = - int(diff // 3600)
			mm = int((diff % 3600) // 60)
		else:
			hh = int(diff // 3600)
			mm = int((diff % 3600) // 60)

		msg += (f'\n\t\t- <b>{pl}</b> ({team}) {roles}:' +
		        f' {pr}, <i>{tm}</i>   <b>{hh}h:{mm}m</b>')

	return msg


def message_with_payment(user, acquisto, pagamento):

	"""
	Crea il messaggio di riepilogo del pagamento.
	Utilizzato all'interno della funzione pago().


	:param user: str, nome della fantasquadra
	:param acquisto: str, giocatore da pagare
	:param pagamento: list, metodo di pagamento

	:return money_db: list, user_input dopo la correzioni dei nomi
	:return message: str, messaggio di riepilogo

	"""

	jpl = ef.jaccard_result(
			acquisto,
			dbf.db_select(table='offers',
			              columns=['offer_player'],
			              where=(f'offer_user = "{user}" AND ' +
			                     'offer_status = "Not Official"')), 3)
	if not jpl:
		return ("Pagamento non riuscito.\n" +
				"Controlla che l'asta sia conclusa e che tu l'abbia vinta.")

	rosa = dbf.db_select(
			table='players',
			columns=['player_name'],
			where=f'player_status = "{user}"')

	for i, pl in enumerate(pagamento):
		try:
			# noinspection PyTypeChecker
			pagamento[i] = int(pl)
			continue
		except ValueError:
			pl2 = ef.jaccard_result(pl, rosa, 3)
			if not pl2:
				return f'Calciatore non riconosciuto nella tua rosa: {pl}'

			tm, rls, pr = dbf.db_select(
					table='players',
					columns=['player_team', 'player_roles', 'player_price'],
					where=f'player_name = "{pl2}"')[0]

			# noinspection PyTypeChecker
			pagamento[i] = (pl2, tm, rls, pr)

	# Nel pagamento proposto dall'user cfg.SEPARo i calciatori dai soldi
	money = 0
	for i in pagamento:
		if type(i) == int:
			money += i

	# Gestisco prima tutta la parte relativa all'acquisto
	off_id, price = dbf.db_select(
			table='offers',
			columns=['offer_id', 'offer_price'],
			where=(f'offer_player = "{jpl}" AND ' +
			       'offer_status = "Not Official"'))[0]

	dbf.db_insert(
			table='pays',
			columns=['pay_user', 'pay_offer',
			         'pay_player', 'pay_price'],
			values=[user, off_id, jpl, price])

	team, roles = dbf.db_select(
			table='players',
			columns=['player_team', 'player_roles'],
			where=f'player_name = "{jpl}"')[0]

	message = ('Stai ufficializzando:\n\n\t\t\t\t\t\t' +
	           f'<b>{jpl}</b> <i>({team})   {roles}</i>\n\n' +
	           f'Prezzo: <b>{price}</b>.\n\nPagamento:\n')

	# Formatto alcuni parametri per poi inviarli come messaggio in chat
	pagamento = [el for el in pagamento if type(el) != int]
	money_db = ', '.join([f'{el[0]} ({el[1]}: {el[3]})' for el in pagamento])
	if money and len(pagamento):
		money_db += f', {money}'
	elif money:
		money_db += f'{money}'

	for pl, tm, rl, pr in pagamento:
		message += f'\n\t\t- <b>{pl}</b> <i>({tm})   {rl}</i>   {pr}'
	if money:
		message += f'\n\t\t- <b>{money}</b>'

	return money_db, message + '\n\n/confermo_pagamento'


def non_svincolato(player):

	"""
	Verifica che il calciatore sia svincolato.

	:param player: str, calciatore

	:return: bool o str

	"""

	status = dbf.db_select(
			table='players',
			columns=['player_status'],
			where=f'player_name = "{player}"')[0]

	if status == 'FREE':
		return False
	else:
		return status


def order_by_role(user):

	"""
	Ordina la lista dei giocatori in base al loro ruolo.
	Utilizzata all'interno di print_rosa().

	:param user: str, fantasquadra

	:return rosa: list, ogni elemento è un tuple

	"""

	roles_dict = {'Por': 1, 'Dc': 2, 'Dd': 2, 'Ds': 2, 'E': 4, 'M': 4, 'C': 5,
	              'W': 6, 'T': 6, 'A': 7, 'Pc': 7}

	rosa = dbf.db_select(
			table='players',
			columns=['player_name', 'player_team',
			         'player_roles', 'player_price'],
			where=f'player_status = "{user}"')

	rosa = [(el[0], el[1], el[2], el[3], roles_dict[el[2].split(';')[0]]) for
	        el in rosa]
	rosa.sort(key=lambda x: x[4])

	rosa = [el[:-1] for el in rosa]

	return rosa


def prezzo_base_automatico(user, ab_id, player_name, autobid_value, active):

	"""
	Presenta un'offerta a prezzo base o comunica la mancanza di un'asta attiva.
	Utilizzata all'interno di confermo_autobid(). L'oggetto del return può
	essere un tuple o una str in modo da distinguere il messaggio da inviare
	in chat privata e quello da inviare nel gruppo ufficiale.
	Utilizzata all'interno di confermo_autobid().

	:param user: str, fantasquadra
	:param ab_id: int, id dell'autobid
	:param player_name: str, nome del calciatore
	:param autobid_value: int, valore autobid
	:param active: bool

	:return: tuple o str a seconda dei casi

	"""

	if active:

		pl_id, pr_base = dbf.db_select(
				table='players',
				columns=['player_id', 'player_price'],
				where=f'player_name = "{player_name}"')[0]

		if autobid_value < pr_base:
			dbf.db_delete(
					table='autobids',
					where=f'autobid_id = {ab_id}')

			return ('Valore autobid troppo basso. ' +
			        f'Prezzo base: {pr_base}'), None

		dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

		dbf.db_insert(
				table='offers',
				columns=['offer_user', 'offer_player', 'offer_player_id',
				         'offer_price', 'offer_dt', 'offer_status'],
				values=[user, player_name, pl_id, pr_base, dt, 'Winning'])

		dbf.db_update(
				table='autobids',
				columns=['autobid_status'],
				values=['Confirmed'],
				where=f'autobid_id = {ab_id}')

		private = ('Autobid impostato ed offerta a prezzo base ' +
		           'ufficializzata.' + cfg.SEPAR + crea_riepilogo_autobid(user))

		group = (f'<i>{user}</i> offre per <b>{player_name}</b>' +
		         cfg.SEPAR + crea_riepilogo(dt))

		return private, group

	else:
		dbf.db_delete(
				table='autobids',
				where=f'autobid_id = {ab_id}')

		return 'Nessuna asta trovata per il calciatore scelto.', None


def select_offer_to_confirm(user):

	"""
	Seleziona l'offerta che l'utente deve confermare, se corretta.
	Ritorna un messaggio esplicativo in caso di assenza di offerte da
	confermare.
	Utilizzata all'interno di confermo_offerta().

	:param user: str, squadra di uno dei partecipanti

	:return of_id: int, id dell'offerta
	:return pl: str, nome del giocatore in questione

	"""

	try:
		of_id, pl = dbf.db_select(
				table='offers',
				columns=['offer_id', 'offer_player'],
				where=f'offer_user = "{user}" AND offer_dt IS NULL')[0]

		return of_id, pl

	except IndexError:
		return False
