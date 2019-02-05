from datetime import datetime, timedelta
import db_functions as dbf
import extra_functions as ef
import selenium_function as sf
from telegram.ext import Updater, CommandHandler


f = open('token.txt', 'r')
updater = Updater(token=f.readline())
f.close()
dispatcher = updater.dispatcher

# True durante il debugging, reindirizza a Testazza tutti i messaggi
# solitamente mandati al gruppo
BLOCK = False
fanta_id = -318148079
polps_id = 67507055

# Tempo in secondi per considerare vinta un'asta
time_window1 = 86400
# Tempo in secondi per ufficializzare
time_window2 = 86400

separ = '\n\n' + '_' * 25 + '\n\n\n'


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
			database=ef.dbase,
			table='offers',
			columns_in=['offer_id', 'offer_user', 'offer_player',
			            'offer_price', 'offer_dt'],
			where='offer_status = "Winning"')

	offers_no = dbf.db_select(
			database=ef.dbase,
			table='offers',
			columns_in=['offer_id', 'offer_user', 'offer_player',
			            'offer_price', 'offer_dt'],
			where='offer_status = "Not Official"')

	# Se tra le offerte aperte ce n'è qualcuna per la quale sono già scadute
	# le 24 ore allora il suo status viene modificato a 'Not Official' ed
	# elimina eventuali autobids attivi per quel calciatore
	for of_id, tm, pl, pr, dt in offers_win:
		dt2 = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
		diff = dt_now - dt2
		if diff.total_seconds() > time_window1:
			offers_no.append((of_id, tm, pl, pr, dt))
			dbf.db_update(
					database=ef.dbase,
					table='offers',
					columns=['offer_status'],
					values=['Not Official'],
					where='offer_id = {}'.format(of_id))
			dbf.db_update(
					database=ef.dbase,
					table='players',
					columns=['player_status'],
					values=[tm],
					where='player_name = "{}"'.format(pl))
			dbf.db_delete(
					database=ef.dbase,
					table='autobids',
					where='autobid_player = "{}"'.format(pl))

	if return_offers:

		# Ridefinisco le due liste trasformando le stringhe in oggetti datetime
		offers_win = [(el[0], el[1], el[2], el[3],
		               datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
		              offers_win if el not in offers_no]

		offers_no = [(el[0], el[1], el[2], el[3],
		              datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
		             offers_no]

		return offers_win, offers_no


def autobid(bot, update, args):

	"""
	Imposta momentaneamente il valore dell'autobid per un calciatore.
	Richiede conferma.

	:param bot:
	:param update:
	:param args: list, input dell'user. Formato: giocatore, valore autobid

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text=('Grazie per avercelo fatto sapere ' +
		                              'ma devi mandarlo in chat privata.'))

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutti gli autobid precedenti non confermati dall'utente
	dbf.db_delete(
			database=ef.dbase,
			table='autobids',
			where=('autobid_user = "{}" AND '.format(user) +
			       'autobid_status IS NULL'))

	result = check_autobid_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		jpl, ab = result

	# Squadra e ruoli
	tm, rl = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_team', 'player_roles'],
			where='player_name = "{}"'.format(jpl))[0]

	# Creo gli oggetti necessari per criptare il valore dell'autobid e li
	# inserisco nel db
	nonce, tag, value = dbf.encrypt_value(ab)
	dbf.db_insert(
			database=ef.dbase,
			table='autobids',
			columns=['autobid_user', 'autobid_player', 'autobid_nonce',
			         'autobid_tag', 'autobid_value'],
			values=[user, jpl, nonce, tag, value])

	message = ('\t\t\t\t<b>{}</b>  <i>{}  {}</i>'.format(jpl, tm, rl) +
	           '\n\nAutobid: {}\n\n\t\t\t\t/confermo_autobid'.format(ab))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=message)


def autorilancio(user, player_name):

	"""
	Controlla che l'user non stia effettuando un autorilancio.

	:param user: str, fantasquadra
	:param player_name: str, nome calciatore

	:return: bool, True se autorilancio altrimenti False

	"""

	offer = dbf.db_select(
			database=ef.dbase,
			table='offers',
			columns_in=['offer_id'],
			where=('offer_user = "{}" AND '.format(user) +
			       'offer_player = "{}" AND '.format(player_name) +
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
			database=ef.dbase,
			table='players',
			columns_in=['player_name'],
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
				database=ef.dbase,
				table='offers',
				columns_in=['offer_id', 'offer_user', 'offer_price'],
				where=('offer_player = "{}" AND '.format(player) +
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
				database=ef.dbase,
				table='autobids',
				where='autobid_id = {}'.format(new_id))

		return ("Valore autobid troppo basso. Impostare un valore superiore" +
		        " all'attuale offerta vincente."), None

	# Se è superiore allora devo controllare che l'user dell'ultima offerta non
	# abbia impostato anche lui un autobid
	else:
		old_ab = dbf.db_select(
				database=ef.dbase,
				table='autobids',
				columns_in=['autobid_id', 'autobid_nonce', 'autobid_tag',
				            'autobid_value'],
				where=('autobid_player = "{}" AND '.format(player) +
				       'autobid_status = "Confirmed"'))

		# Caso 1: non c'è autobid ed il detentore dell'offerta è un avversario.
		# In questo caso l'avversario perde l'offerta a favore del nuovo user.
		# Il valore della nuova offerta sarà automaticamente uguale ad 1
		# fantamilione in più rispetto alla precedente
		if not old_ab and user != last_user:

			dbf.db_update(
					database=ef.dbase,
					table='offers',
					columns=['offer_status'],
					values=['Lost'],
					where='offer_id = {}'.format(last_id))

			dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

			pl_id = dbf.db_select(
					database=ef.dbase,
					table='players',
					columns_in=['player_id'],
					where='player_name = "{}"'.format(player))[0]

			dbf.db_insert(
					database=ef.dbase,
					table='offers',
					columns=['offer_user', 'offer_player', 'offer_player_id',
					         'offer_price', 'offer_dt', 'offer_status'],
					values=[user, player, pl_id, last_offer + 1, dt, 'Winning'])

			# Cancello l'autobid nel caso venga raggiunto il suo valore
			if new_ab == last_offer + 1:
				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))

				private = ('Hai dovuto utilizzare tutto il tuo autobid. ' +
				           'Reimposta un valore più alto nel caso volessi ' +
				           'continuare ad usarlo.' + separ +
				           crea_riepilogo_autobid(user))
			else:
				dbf.db_update(
						database=ef.dbase,
						table='autobids',
						columns=['autobid_status'],
						values=['Confirmed'],
						where='autobid_id = {}'.format(new_id))

				private = ('Offerta aggiornata ed autobid impostato ' +
				           'correttamente.' + separ +
				           crea_riepilogo_autobid(user))

			group = ('<i>{}</i> rilancia per <b>{}</b>.'.format(user, player) +
			         separ + crea_riepilogo(dt))

			return private, group

		# Caso 2: non c'è autobid ed il detentore dell'offerta è lo stesso user.
		# In questo caso viene semplicemente impostato l'autobid
		elif not old_ab and user == last_user:

			dbf.db_update(
					database=ef.dbase,
					table='autobids',
					columns=['autobid_status'],
					values=['Confirmed'],
					where='autobid_id = {}'.format(new_id))

			return ('Autobid impostato correttamente.' + separ +
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
						database=ef.dbase,
						table='offers',
						columns=['offer_status'],
						values=['Lost'],
						where='offer_id = {}'.format(last_id))

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(old_id))

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				pl_id = dbf.db_select(
						database=ef.dbase,
						table='players',
						columns_in=['player_id'],
						where='player_name = "{}"'.format(player))[0]

				dbf.db_insert(
						database=ef.dbase,
						table='offers',
						columns=['offer_user', 'offer_player',
						         'offer_player_id',
						         'offer_price', 'offer_dt',
						         'offer_status'],
						values=[user, player, pl_id, old_ab + 1, dt,
						        'Winning'])

				if new_ab == old_ab + 1:
					dbf.db_delete(
							database=ef.dbase,
							table='autobids',
							where='autobid_id = {}'.format(new_id))

					private = ('Hai dovuto utilizzare tutto il tuo autobid. ' +
					           'Reimposta un valore più alto nel caso ' +
					           'volessi continuare ad usarlo.' + separ +
					           crea_riepilogo_autobid(user))
				else:
					dbf.db_update(
							database=ef.dbase,
							table='autobids',
							columns=['autobid_status'],
							values=['Confirmed'],
							where='autobid_id = {}'.format(new_id))

					private = ('Offerta aggiornata ed autobid impostato ' +
					           'correttamente.' + separ +
					           crea_riepilogo_autobid(user))

				group = ('<i>{}</i> rilancia '.format(user) +
						 'per <b>{}</b>.'.format(player) + separ +
						 crea_riepilogo(dt))

				return private, group

			# Caso 4: il nuovo autobid supera il vecchio ed il detentore
			# dell'offerta è lo stesso user. Viene aggiornato l'autobid
			# precedente al nuovo valore più alto
			elif new_ab > old_ab and user == last_user:

				nonce, tag, value = dbf.encrypt_value(str(new_ab))
				dbf.db_update(
						database=ef.dbase,
						table='autobids',
						columns=['autobid_nonce', 'autobid_tag',
						         'autobid_value'],
						values=[nonce, tag, value],
						where='autobid_id = {}'.format(old_id))

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))

				return ('Hai aumentato il tuo autobid per {} '.format(player) +
				        'da {} a {}.'.format(old_ab, new_ab) + separ +
				        crea_riepilogo_autobid(user)), None

			# Caso 5: il nuovo autobid non supera il vecchio ed il detentore
			# dell'offerta è un avversario. Il nuovo autobid non viene
			# confermato e l'offerta del detentore viene aggiornata ad un
			# valore pari all'autobid tentato dall'user più 1 fantamilione
			elif new_ab < old_ab and user != last_user:

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))

				dbf.db_update(
						database=ef.dbase,
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[new_ab + 1, dt],
						where='offer_id = {}'.format(last_id))

				if old_ab == new_ab + 1:
					dbf.db_delete(
							database=ef.dbase,
							table='autobids',
							where='autobid_id = {}'.format(old_id))

				private = 'Autobid troppo basso.'
				group = ('<i>{}</i> ha tentato un rilancio'.format(user) +
						 ' per <b>{}</b>.'.format(player) + separ +
						 crea_riepilogo(dt))

				return private, group

			# Caso 6: il nuovo autobid non supera il vecchio ed il detentore
			# dell'offerta è lo stesso user. Viene aggiornato l'autobid
			# precedente al nuovo valore più basso
			elif new_ab < old_ab and user == last_user:

				nonce, tag, value = dbf.encrypt_value(str(new_ab))
				dbf.db_update(
						database=ef.dbase,
						table='autobids',
						columns=['autobid_nonce', 'autobid_tag',
						         'autobid_value'],
						values=[nonce, tag, value],
						where='autobid_id = {}'.format(old_id))

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))

				return ('Hai diminuito il tuo autobid per {} '.format(player) +
				        'da {} a {}.'.format(old_ab, new_ab) + separ +
				        crea_riepilogo_autobid(user)), None

			# Caso 7: il nuovo autobid è uguale al vecchio ed il detentore
			# dell'offerta è un avversario. Viene convalidato quello del
			# detentore per averlo impostato in anticipo
			elif new_ab == old_ab and user != last_user:

				dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

				sex = dbf.db_select(
						database=ef.dbase,
						table='teams',
						columns_in=['team_sex'],
						where='team_name = "{}"'.format(last_user))[0]

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(old_id))

				dbf.db_update(
						database=ef.dbase,
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[new_ab, dt],
						where='offer_id = {}'.format(last_id))

				private = ("Autobid uguale a quello di {}.".format(last_user) +
				           " Ha la precedenza " + sex + " perché l'ha " +
				           "impostato prima.")
				group = ('<i>{}</i> ha tentato un rilancio'.format(user) +
						 ' per <b>{}</b>.'.format(player) + separ +
						 crea_riepilogo(dt))

				return private, group

			# Caso 8: il nuovo autobid è uguale al vecchio ed il detentore
			# dell'offerta è lo stesso user.
			elif new_ab == old_ab and user == last_user:
				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
						where='autobid_id = {}'.format(new_id))
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
			database=ef.dbase,
			table='players',
			columns_in=['player_name'],
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
			database=ef.dbase,
			table='offers',
			columns_in=['offer_price'],
			where='offer_id = {}'.format(offer_id))[0]

	# Prendo dal db i dettagli dell'ultima offerta valida per questo
	# calciatore, qualora ci sia
	try:
		last_id, last_user, last_offer = dbf.db_select(
				database=ef.dbase,
				table='offers',
				columns_in=['offer_id', 'offer_user', 'offer_price'],
				where=('offer_player = "{}" AND '.format(player) +
				       'offer_status = "Winning"'))[0]
	except IndexError:
		last_id = 0
		last_user = None
		last_offer = 0

	# Se si tratta di prima offerta, ne confronto il valore con il prezzo base
	# del calciatore ed aggiorno il db
	if not last_offer:
		price = dbf.db_select(
				database=ef.dbase,
				table='players',
				columns_in=['player_price'],
				where='player_name = "{}"'.format(player))[0]
		if offer < price:
			dbf.db_delete(
					database=ef.dbase,
					table='offers',
			        where='offer_id = {}'.format(offer_id))

			return 'Offerta troppo bassa. Quotazione: {}'.format(price)
		else:

			dbf.db_update(
					database=ef.dbase,
					table='offers',
					columns=['offer_dt', 'offer_status'],
					values=[dt, 'Winning'],
					where='offer_id = {}'.format(offer_id))

			private = 'Offerta aggiornata correttamente.'

			group = ('<i>{}</i> offre per '.format(user) +
			         '<b>{}</b>.'.format(player) + separ + crea_riepilogo(dt))

			return private, group

	# Se si tratta di rilancio, controllo che l'offerta superi quella già
	# esistente
	else:
		if offer <= last_offer:
			dbf.db_delete(
					database=ef.dbase,
					table='offers',
			        where='offer_id = {}'.format(offer_id))

			return ('Offerta troppo bassa. ' +
			        'Ultimo rilancio: {}, {}'.format(last_offer, last_user))
		else:
			# Se la supera, resta da confrontarla con un eventuale autobid.
			# Quindi seleziono l'autobid già impostato dall'altro user oppure,
			# qualora non esista, assegno valore nullo ad alcune variabili in
			# modo da gestire il codice successivo
			try:
				iid, ab_user, nonce, tag, encr_value = dbf.db_select(
						database=ef.dbase,
						table='autobids',
						columns_in=['autobid_id', 'autobid_user',
						            'autobid_nonce', 'autobid_tag',
						            'autobid_value'],
						where='autobid_player = "{}"'.format(player))[0]
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
						database=ef.dbase,
						table='offers',
				        where='offer_id = {}'.format(offer_id))
				dbf.db_update(
						database=ef.dbase,
						table='offers',
						columns=['offer_price', 'offer_dt'],
						values=[offer + 1, dt],
						where='offer_id = {}'.format(last_id))
				if offer + 1 == last_ab:
					dbf.db_delete(
							database=ef.dbase,
					        table='autobids',
					        where='autobid_id = {}'.format(iid))

				private = ("Offerta troppo bassa. Non hai superato" +
				           " l'autobid di {}.".format(ab_user))

				group = ('<i>{}</i> ha tentato un rilancio '.format(user) +
				         'per <b>{}</b>.'.format(player) +
				         separ + crea_riepilogo(dt))

				return private, group

			# Se invece l'offerta supera l'ultimo autobid allora cancello tale
			# autobid dal db ed aggiorno tutti gli altri parametri
			else:

				dbf.db_delete(
						database=ef.dbase,
						table='autobids',
				        where='autobid_id = {}'.format(iid))

				dbf.db_update(
						database=ef.dbase,
						table='offers',
						columns=['offer_dt', 'offer_status'],
						values=[dt, 'Winning'],
						where='offer_id = {}'.format(offer_id))

				dbf.db_update(
						database=ef.dbase,
						table='offers',
						columns=['offer_status'],
						values=['Lost'],
						where='offer_id = {}'.format(last_id))

				private = 'Offerta aggiornata correttamente.'

				group = ('<i>{}</i> ha rilanciato '.format(user) +
				         'per <b>{}</b>.'.format(player) + separ +
				         crea_riepilogo(dt))

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


def confermo_autobid(bot, update):

	"""
	Confronta il valore impostato con quello dell'ultima offerta valida. Se
	tutto ok, aggiorna il db.

	:param bot:
	:param update:
	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if BLOCK:
		group_id = polps_id
	else:
		group_id = fanta_id

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Decripto il valore impostato
	new_id, pl, nonce, tag, encr_value = dbf.db_select(
			database=ef.dbase,
			table='autobids',
			columns_out=['autobid_user', 'autobid_status'],
			where=('autobid_user = "{}" '.format(user) +
			       'AND autobid_status IS NULL'))[0]
	new_ab = int(dbf.decrypt_value(nonce, tag, encr_value).decode())

	# Esamino tutti i possibili casi
	private, group = check_autobid_value(user, pl, new_id, new_ab)

	if private:
		bot.send_message(parse_mode='HTML', chat_id=chat_id, text=private)
	if group:
		bot.send_message(parse_mode='HTML', chat_id=group_id, text=group)


def confermo_eliminazione(bot, update):

	"""
	Elimina definitivamente dal db l'autobid scelto.
	Utilizzata all'ainterno di elimino_autobid().

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	ab_to_delete = dbf.db_select(
			database=ef.dbase,
			table='elimina',
			columns_in=['elimina_ab'],
			where='elimina_user = "{}"'.format(user))
	if not ab_to_delete:
		return bot.send_message(chat_id=chat_id,
		                        text='Non hai autobid da eliminare.')

	dbf.db_delete(
			database=ef.dbase,
			table='autobids',
	        where='autobid_id = {}'.format(ab_to_delete[0]))

	dbf.db_delete(
			database=ef.dbase,
			table='elimina',
	        where='elimina_ab = {}'.format(ab_to_delete[0]))

	message = 'Autobid eliminato' + separ + crea_riepilogo_autobid(user)

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def confermo_offerta(bot, update):

	"""
	Conferma l'offerta effettuata (se valida) ed aggiorna il db di conseguenza.
	Infine manda un messaggio in chat con tutte le offerte aperte e chiuse.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if BLOCK:
		group_id = polps_id
	else:
		group_id = fanta_id

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Controllo che ci siano offerte da confermare
	try:
		of_id, pl = select_offer_to_confirm(user)
	except TypeError:
		return bot.send_message(chat_id=chat_id,
								text='Nulla da confermare per {}'.format(user))

	# Controllo che il calciatore sia svincolato
	if non_svincolato(pl):
		dbf.db_delete(
				database=ef.dbase,
				table='offers',
				where=('offer_user = "{}" AND '.format(user) +
				       'offer_status IS NULL'))
		return bot.send_message(chat_id=chat_id,
		                        text='Giocatore non svincolato ({}).'.
		                        format(non_svincolato(pl)))

	# Controllo che non si tratti di autorilancio
	if autorilancio(user, pl):
		dbf.db_delete(
				database=ef.dbase,
				table='offers',
				where=('offer_user = "{}" AND '.format(user) +
				       'offer_status IS NULL'))
		return bot.send_message(chat_id=chat_id,
		                        text="L'ultima offerta è già tua.")

	# Controllo che l'offerta superi l'ultimo rilancio ed eventuali autobids
	result = check_offer_value(user, of_id, pl, dt)

	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		# Elimino eventuali offerte non confermate da altri user per lo stesso
		# calciatore
		dbf.db_delete(
				database=ef.dbase,
				table='offers',
				where='offer_player = "{}"'.format(pl) +
				      'AND offer_status IS NULL AND ' +
				      'offer_user != "{}"'.format(user))

		pvt, grp = result
		bot.send_message(chat_id=chat_id, text=pvt)
		return bot.send_message(parse_mode='HTML', chat_id=group_id, text=grp)


def confermo_pagamento(bot, update):

	"""
	Conferma il pagamento di un'offerta ufficiale ed aggiorna il db di
	conseguenza. Innanzitutto controlla se i milioni offerti sono sufficienti,
	dopodichè controlla se si ha effettivamente il budget per completare il
	pagamento. Se l'offerta risulta valida a tutti gli effetti, verrà
	aggiornato il budget della squadra in questione, lo status dei calciatori
	coinvolti, la tabella "offers" e la tabella "pays".

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if BLOCK:
		group_id = polps_id
	else:
		group_id = fanta_id

	user = select_user(update)

	# Controllo ci sia il pagamento e, se sì, lo seleziono.
	try:
		pay_id, pl, pr, mn = dbf.db_select(
				database=ef.dbase,
				table='pays',
				columns_in=['pay_id', 'pay_player', 'pay_price', 'pay_money'],
				where='pay_user = "{}" AND pay_status IS NULL'.
					format(user))[0]
	except IndexError:
		return bot.send_message(chat_id=chat_id,
		                        text='Nulla da confermare per {}'.format(user))

	# Analizzo il metodo di pagamento proposto e controllo che sia sufficiente
	# a coprire la spesa
	mn = mn.split(', ')
	temp_bud = 0
	for i in mn:
		try:
			temp_bud += int(i)
		except ValueError:
			temp_bud += int(i.split(': ')[1][:-1])

	if temp_bud < pr:
		dbf.db_delete(
				database=ef.dbase,
				table='pays',
				where='pay_user = "{}" AND pay_player = "{}"'.format(user, pl))
		return bot.send_message(chat_id=chat_id,
		                        text=('Offerta insufficiente.\n' +
		                              'Milioni mancanti: {}'.format(
				                              pr - temp_bud)))

	# Sommo al budget della fantasquadra il prezzo dei giocatori utilizzati
	# nel pagamento, se presenti, e che saranno quindi ceduti
	budget = dbf.db_select(
			database=ef.dbase,
			table='budgets',
			columns_in=['budget_value'],
			where='budget_team = "{}"'.format(user))[0]

	new_budget = budget
	for i in mn:
		try:
			int(i)
		except ValueError:
			new_budget += dbf.db_select(
					database=ef.dbase,
					table='players',
					columns_in=['player_price'],
					where='player_name = "{}"'.format(i.split(' (')[0]))[0]

	# Qualora l'offerta sia valida, aggiorno varie voci nel db sia del
	# calciatore acquistato che di quelli ceduti, se presenti
	if new_budget < pr:
		dbf.db_delete(
				database=ef.dbase,
				table='pays',
				where='pay_user = "{}" AND pay_player = "{}"'.format(user, pl))
		return bot.send_message(chat_id=chat_id,
		                        text='Budget insufficiente')
	else:
		dbf.db_update(
				database=ef.dbase,
				table='budgets',
				columns=['budget_value'],
				values=[new_budget - pr],
				where='budget_team = "{}"'.format(user))

		dbf.db_update(
				database=ef.dbase,
				table='players',
				columns=['player_status'],
				values=[user],
				where='player_name = "{}"'.format(pl))

		dbf.db_update(
				database=ef.dbase,
				table='offers',
				columns=['offer_status'],
				values=['Official'],
				where='offer_player = "{}" AND offer_status = "Not Official"'.
					format(pl))

		dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		dbf.db_update(
				database=ef.dbase,
				table='pays',
				columns=['pay_dt', 'pay_status'],
				values=[dt, 'Confirmed'],
				where='pay_player = "{}"'.format(pl))

		for i in mn:
			try:
				int(i)
			except ValueError:
				dbf.db_update(
						database=ef.dbase,
						table='players',
						columns=['player_status'],
						values=['FREE'],
						where='player_name = "{}"'.format(i.split(' (')[0]))

	message = ('<i>{}</i> ha ufficializzato '.format(user) +
	           '<b>{}</b> a {}.'.format(pl, pr) +
	           '\nPagamento: {}\n'.format(', '.join(mn)))

	if budget == new_budget - pr:
		message += 'Il budget resta {}'.format(budget)
	else:
		message += 'Il budget passa da {} a {}.'.format(budget,
		                                                new_budget - pr)

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	bot.send_message(chat_id=chat_id,
	                 text='Pagamento effettuato correttamente.')

	bot.send_message(parse_mode='HTML', chat_id=group_id,
	                 text=(message + separ + crea_riepilogo(dt)))

	# sf.aggiorna_rosa_online(user, (pl, pr), mn)


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

	message1 = message_with_offers(offers_win, time_window1, dt_now, message1)
	message2 = message_with_offers(offers_no, time_window1 + time_window2,
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
			database=ef.dbase,
			table='autobids',
			columns_out=['autobid_id', 'autobid_user', 'autobid_status'],
			where=('autobid_user = "{}" AND '.format(user) +
			       'autobid_status = "Confirmed"'))
	if not autobids:
		return 'Nessun autobid attivo.'

	message = 'I tuoi autobid attivi sono:\n\n'
	for pl, nonce, tag, encr_ab in autobids:
		decr_ab = int(dbf.decrypt_value(nonce, tag, encr_ab).decode())
		message += '\t\t\t\t<b>{}</b>: {}\n'.format(pl, decr_ab)

	return message


def elimino_autobid(bot, update, args):

	"""
	Inserisce nella tabella "elimina" del db l'autobid da cancellare.
	Richiede conferma.

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if update.message.chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	# Elimino tutte le proposte di cancellazione non confermate dall'user
	dbf.db_delete(
			database=ef.dbase,
			table='elimina',
			where='elimina_user = "{}"'.format(user))

	# Seleziono tutti gli autobids dell'user
	autobids = dbf.db_select(
			database=ef.dbase,
			table='autobids',
			columns_in=['autobid_player'],
			where='autobid_user = "{}"'.format(user))
	if not autobids:
		return bot.send_message(chat_id=chat_id,
		                        text='Non hai autobid impostati.')

	# Controllo che il comando sia inviato correttamente
	pl = ''.join(args).split(',')
	if not pl[0] or len(pl) != 1:
		return bot.send_message(chat_id=chat_id,
		                        text=('Formato errato. ' +
		                              'Es: /elimina_autobid petagna'))

	jpl = ef.jaccard_result(pl[0], autobids, 3)
	if not jpl:
		return bot.send_message(chat_id=chat_id,
		                        text='Giocatore non riconosciuto.')

	ab = dbf.db_select(
			database=ef.dbase,
			table='autobids',
			columns_in=['autobid_id'],
			where=('autobid_user = "{}" AND '.format(user) +
			       'autobid_player = "{}"'.format(jpl)))[0]

	dbf.db_insert(
			database=ef.dbase,
			table='elimina',
			columns=['elimina_ab', 'elimina_user'],
			values=[ab, user])

	message = ("Stai eliminando l'autobid per <b>{}</b>:".format(jpl) +
	           "\n\n\t\t\t\t/confermo_eliminazione")

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def info(bot, update):

	"""
	Invia in chat le info sui comandi.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""
	chat_id = update.message.chat_id
	if update.message.chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	g = open('info.txt', 'r')
	content = g.readlines()
	g.close()

	message = ''
	for row in content:
		row = row.replace('xx\n', ' ')
		message += row

	sf.logger.info('/INFO - {}'.format(select_user(update)))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def info_autobid(bot, update):

	"""
	Invia in chat le istruzioni sul funzionamento dell'autobid.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if update.message.chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	g = open('info_autobid.txt', 'r')
	content = g.readlines()
	g.close()

	message = ''
	for row in content:
		row = row.replace('xx\n', ' ')
		message += row

	sf.logger.info('/INFO_AUTOBID - {}'.format(select_user(update)))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def inizio_mercato(bot, update):

	bot.send_message(chat_id=fanta_id, text='Potete iniziare, stronzi!')


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
				database=ef.dbase,
				table='players',
				columns_in=['player_team', 'player_roles'],
				where='player_name = "{}"'.format(pl))[0]
		dt_plus = dt + timedelta(seconds=shift)
		diff = (dt_plus - dt_now).total_seconds()
		if diff < 0:
			diff = abs(diff)
			hh = - int(diff // 3600)
			mm = int((diff % 3600) // 60)
		else:
			hh = int(diff // 3600)
			mm = int((diff % 3600) // 60)

		msg += ('\n\t\t- <b>{}</b> ({}) {}:'.format(pl, team, roles) +
		        ' {}, <i>{}</i>  '.format(pr, tm) +
		        ' <b>{}h:{}m</b>'.format(hh, mm))

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
			dbf.db_select(
					database=ef.dbase,
					table='offers',
					columns_in=['offer_player'],
					where=('offer_user = "{}" AND '.format(user) +
					       'offer_status = "Not Official"')), 3)
	if not jpl:
		return ("Pagamento non riuscito.\n" +
				"Controlla che l'asta sia conclusa e che tu l'abbia vinta.")

	rosa = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_name'],
			where='player_status = "{}"'.format(user))

	for i, pl in enumerate(pagamento):
		try:
			# noinspection PyTypeChecker
			pagamento[i] = int(pl)
			continue
		except ValueError:
			pl2 = ef.jaccard_result(pl, rosa, 3)
			if not pl2:
				return ('Calciatore non riconosciuto nella tua ' +
				        'rosa: {}'.format(pl))

			tm, rls, pr = dbf.db_select(
					database=ef.dbase,
					table='players',
					columns_in=['player_team', 'player_roles',
					            'player_price'],
					where='player_name = "{}"'.format(pl2))[0]

			# noinspection PyTypeChecker
			pagamento[i] = (pl2, tm, rls, pr)

	# Nel pagamento proposto dall'user separo i calciatori dai soldi
	money = 0
	for i in pagamento:
		if type(i) == int:
			money += i

	# Gestisco prima tutta la parte relativa all'acquisto
	off_id, price = dbf.db_select(
			database=ef.dbase,
			table='offers',
			columns_in=['offer_id', 'offer_price'],
			where=('offer_player = "{}" AND '.format(jpl) +
			       'offer_status = "Not Official"'))[0]

	dbf.db_insert(
			database=ef.dbase,
			table='pays',
			columns=['pay_user', 'pay_offer',
			         'pay_player', 'pay_price'],
			values=[user, off_id, jpl, price])

	team, roles = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_team', 'player_roles'],
			where='player_name = "{}"'.format(jpl))[0]

	message = ('Stai ufficializzando:\n\n\t\t\t\t\t\t' +
	           '<b>{}</b> <i>({})   {}</i>\n\n'.format(jpl, team, roles) +
	           'Prezzo: <b>{}</b>.\n\nPagamento:\n'.format(price))

	# Formatto alcuni parametri per poi inviarli come messaggio in chat
	pagamento = [el for el in pagamento if type(el) != int]
	money_db = ', '.join(['{} ({}: {})'.format(el[0], el[1], el[3]) for el in
	                      pagamento])
	if money and len(pagamento):
		money_db += ', {}'.format(money)
	elif money:
		money_db += '{}'.format(money)

	for pl, tm, rl, pr in pagamento:
		message += '\n\t\t- <b>{}</b> <i>({})   {}</i>   {}'.format(pl, tm,
		                                                            rl, pr)
	if money:
		message += '\n\t\t- <b>{}</b>'.format(money)

	return money_db, message + '\n\n/confermo_pagamento'


def non_svincolato(player):

	"""
	Verifica che il calciatore sia svincolato.

	:param player: str, calciatore

	:return: bool o str

	"""

	status = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_status'],
			where='player_name = "{}"'.format(player))[0]

	if status == 'FREE':
		return False
	else:
		return status


def offro(bot, update, args):

	"""
	Inserisce nella tabella "offers" del db la nuova offerta presentata.
	Nel caso in cui l'offerta sia presentata in modo sbagliato invia in chat un
	messaggio di avviso.
	Lo status dell'offerta del db sarà NULL, in attesa di conferma.

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutte le offerte precedenti non confermate dall'utente
	dbf.db_delete(
			database=ef.dbase,
			table='offers',
			where='offer_user = "{}" '.format(user) +
				  'AND offer_status IS NULL')

	# Controllo che il formato sia giusto
	result = check_offer_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		offer, pl = result

	# Aggiorno il db con i parametri che mancano
	pl_id = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_id'],
			where='player_name = "{}"'.format(pl))[0]

	team, roles, price = dbf.db_select(
			database=ef.dbase,
			table='players',
			columns_in=['player_team', 'player_roles', 'player_price'],
			where='player_name = "{}"'.format(pl))[0]

	dbf.db_insert(
			database=ef.dbase,
			table='offers',
			columns=['offer_user', 'offer_player', 'offer_player_id',
			         'offer_price'],
			values=[user, pl, pl_id, offer])

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
							text='Offri <b>{}</b> per:\n\n\t\t'.format(offer) +
							     '<b>{}   ({})   {}</b>'.format(pl, team,
							                                    roles) +
							'\n\n/confermo_offerta')


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
			database=ef.dbase,
			table='players',
			columns_in=['player_name', 'player_team',
			            'player_roles', 'player_price'],
			where='player_status = "{}"'.format(user))

	rosa = [(el[0], el[1], el[2], el[3], roles_dict[el[2].split(';')[0]]) for
	        el in rosa]
	rosa.sort(key=lambda x: x[4])

	rosa = [el[:-1] for el in rosa]

	return rosa


def pago(bot, update, args):

	"""
	Aggiorna la tabella "pays" del db con lo status di "Not Confirmed".

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutte i pagamenti precedenti non confermati dall'utente
	dbf.db_delete(
			database=ef.dbase,
			table='pays',
			where='pay_user = "{}" AND pay_status IS NULL'.format(user))

	# Controllo che il formato sia corretto
	result = check_pago_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		acquisto, pagamento = result

	# Creo il messaggio di conferma ed aggiorno il db con il pagamento
	# provvisorio
	result = message_with_payment(user, acquisto, pagamento)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		money_db, message = result

	dbf.db_update(
			database=ef.dbase,
			table='pays',
			columns=['pay_money'],
			values=[money_db],
			where='pay_user = "{}" AND pay_status IS NULL'.format(user))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def prezzo(bot, update, args):

	"""
	Restituisce il prezzo di un calciatore.

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	args = ''.join(args).split(',')

	if len(args) != 2:
		return bot.send_message(chat_id=chat_id,
		                        text=('Formato non corretto.\n' +
		                        'Ex: /prezzo higuain, milan'))

	pl, tm = args

	tm = ef.jaccard_result(
			tm, dbf.db_select(
					database=ef.dbase,
					table='players',
			        columns_in=['player_team']), 3)
	if not tm:
		return bot.send_message(chat_id=chat_id,
		                        text='Squadra non riconosciuta, riprova.')

	pl = ef.jaccard_result(pl,
	                       dbf.db_select(
			                       database=ef.dbase,
			                       table='players',
			                       columns_in=['player_name'],
	                               where='player_team = "{}"'.format(tm)), 3)
	if not pl:
		return bot.send_message(chat_id=chat_id,
		                        text='Calciatore non riconosciuto, riprova.')

	rl, pr, st = dbf.db_select(
			database=ef.dbase,
			table='players',
            columns_in=['player_roles', 'player_price', 'player_status'],
			where='player_name = "{}"'.format(pl))[0]

	if st == 'FREE':
		st = 'Svincolato'

	message = ('\t\t\t\t<b>{}</b> <i>({})   {}</i>\n\n'.format(pl, tm, rl) +
	           'Squadra: <i>{}</i>\n'.format(st) +
	           'Prezzo: <b>{}</b>'.format(pr))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


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
				database=ef.dbase,
				table='players',
				columns_in=['player_id', 'player_price'],
				where='player_name = "{}"'.format(player_name))[0]

		if autobid_value < pr_base:
			dbf.db_delete(
					database=ef.dbase,
					table='autobids',
					where='autobid_id = {}'.format(ab_id))

			return ('Valore autobid troppo basso. ' +
			        'Prezzo base: {}'.format(pr_base)), None

		dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

		dbf.db_insert(
				database=ef.dbase,
				table='offers',
				columns=['offer_user', 'offer_player', 'offer_player_id',
				         'offer_price', 'offer_dt', 'offer_status'],
				values=[user, player_name, pl_id, pr_base, dt, 'Winning'])

		dbf.db_update(
				database=ef.dbase,
				table='autobids',
				columns=['autobid_status'],
				values=['Confirmed'],
				where='autobid_id = {}'.format(ab_id))

		private = ('Autobid impostato ed offerta a prezzo base ' +
		           'ufficializzata.' + separ + crea_riepilogo_autobid(user))

		group = ('<i>{}</i> offre per <b>{}</b>'.format(user, player_name) +
		         separ + crea_riepilogo(dt))

		return private, group

	else:
		dbf.db_delete(
				database=ef.dbase,
				table='autobids',
				where='autobid_id = {}'.format(ab_id))

		return 'Nessuna asta trovata per il calciatore scelto.', None


def print_rosa(bot, update):

	"""
	Invia in chat un messaggio con la rosa dell'user, il numero di giocatori ed
	il budget disponibile.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	message = '<i>{}</i> :\n'.format(user)

	rosa = order_by_role(user)

	for pl, tm, rl, pr in rosa:
		line = '\n\t\t\t<b>{}</b> ({})   {}     {}'.format(pl, tm, rl, pr)
		message += line

	budget = dbf.db_select(
			database=ef.dbase,
			table='budgets',
			columns_in=['budget_value'],
			where='budget_team = "{}"'.format(user))[0]

	message += ('\n\nNumero di giocatori: <b>{}</b>\n'.format(len(rosa)) +
	            'Milioni disponibili: <b>{}</b>'.format(budget))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def riepilogo(bot, update):

	"""
	Invia in chat il riepilogo delle offerte aperte, chiuse ma non ancora
	ufficializzate e quelle già ufficializzate.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=crea_riepilogo(dt))


def riepilogo_autobid(bot, update):

	"""
	Manda in chat gli autobid attivi dell'user che invia il comando.

	:param bot:
	:param update:

	:return: str, messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=crea_riepilogo_autobid(user))


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
				database=ef.dbase,
				table='offers',
				columns_in=['offer_id', 'offer_player'],
				where='offer_user = "{}" AND offer_dt IS NULL'.
					format(user))[0]

		return of_id, pl

	except IndexError:
		return False


def select_user(update):

	"""
	Mappa il nome di colui che invia il comando con la rispettiva fantasquadra.
	Utilizzata ovunque.

	:param update:

	:return user: str, nome fantasquadra

	"""

	return dbf.db_select(
			database=ef.dbase,
			table='teams',
			columns_in=['team_name'],
			where='team_member = "{}"'.
				format(update.message.from_user.first_name))[0]


def ufficiali(bot, update):

	"""
	Crea il messaggio con le offerte già ufficializzate.

	:return message: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == fanta_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	message = 'Ufficializzazioni:\n'

	uffic = dbf.db_select(
			database=ef.dbase,
			table='offers',
			columns_in=['offer_id', 'offer_user',
			            'offer_player', 'offer_price'],
			where='offer_status = "Official"')

	for off_id, user, pl, pr in uffic:

		tm = dbf.db_select(
				database=ef.dbase,
				table='players',
				columns_in=['player_team'],
				where='player_name = "{}"'.format(pl))[0]

		pagamento = dbf.db_select(
				database=ef.dbase,
				table='pays',
				columns_in=['pay_money'],
				where='pay_offer = {}'.format(off_id))[0]

		message += ('\n\t\t\t\t- <i>{}</i> '.format(user) +
		            'acquista <b>{}</b> ({}) a {}. '.format(pl, tm, pr) +
		            'Pagamento: <i>{}</i>.\n'.format(pagamento))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


# inizio = updater.job_queue
# inizio.run_once(inizio_mercato, when=time(00, 00, 00))

autobid_handler = CommandHandler('autobid', autobid, pass_args=True)
confermo_autobid_handler = CommandHandler('confermo_autobid', confermo_autobid)
confermo_eliminazione_handler = CommandHandler('confermo_eliminazione',
                                               confermo_eliminazione)
confermo_offerta_handler = CommandHandler('confermo_offerta', confermo_offerta)
confermo_pagamento_handler = CommandHandler('confermo_pagamento',
                                            confermo_pagamento)
elimino_autobid_handler = CommandHandler('elimino_autobid', elimino_autobid,
                                         pass_args=True)
info_handler = CommandHandler('info', info)
info_autobid_handler = CommandHandler('info_autobid', info_autobid)
offro_handler = CommandHandler('offro', offro, pass_args=True)
pago_handler = CommandHandler('pago', pago, pass_args=True)
prezzo_handler = CommandHandler('prezzo', prezzo, pass_args=True)
riepilogo_handler = CommandHandler('riepilogo', riepilogo)
riepilogo_autobid_handler = CommandHandler('riepilogo_autobid',
                                           riepilogo_autobid)
rosa_handler = CommandHandler('rosa', print_rosa)
ufficiali_handler = CommandHandler('ufficiali', ufficiali)

dispatcher.add_handler(autobid_handler)
dispatcher.add_handler(confermo_autobid_handler)
dispatcher.add_handler(confermo_eliminazione_handler)
dispatcher.add_handler(confermo_offerta_handler)
dispatcher.add_handler(confermo_pagamento_handler)
dispatcher.add_handler(elimino_autobid_handler)
dispatcher.add_handler(info_handler)
dispatcher.add_handler(info_autobid_handler)
dispatcher.add_handler(offro_handler)
dispatcher.add_handler(pago_handler)
dispatcher.add_handler(prezzo_handler)
dispatcher.add_handler(riepilogo_handler)
dispatcher.add_handler(riepilogo_autobid_handler)
dispatcher.add_handler(rosa_handler)
dispatcher.add_handler(ufficiali_handler)

updater.start_polling()
updater.idle()
