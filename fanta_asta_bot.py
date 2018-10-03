from datetime import datetime, timedelta
import db_functions as dbf
import extra_functions as ef
import selenium_function as sf
from telegram.ext import Updater, CommandHandler


f = open('token.txt', 'r')
updater = Updater(token=f.readline())
f.close()
dispatcher = updater.dispatcher
BLOCK = False
group_id = -318148079
# group_id = 67507055
polps_id = 67507055
jac_message = ("Impossibile riconoscere l'input. Correggere eventuali errori" +
               " di scrittura o controllare che l'ordine di inserimento " +
               "sia corretto.")


def aaa(bot, update):

	user = select_user(update)
	dbf.db_update(
			table='offers',
			columns=['offer_status'],
			values=['Not Official'],
			where='offer_user = "{}" AND offer_status = "Winning"'.format(user))

	return bot.send_message(chat_id=update.message.chat_id,
	                        text='Puoi pagare')


def aggiorna_offerte_chiuse(dt_now):

	"""
	Confronta i tempi trascorsi da ogni offerta e chiude quelle che hanno già
	raggiunto o superato le 24 ore necessarie.
	Utilizzata all'interno di crea_riepilogo() e pago().

	:param dt_now: datetime, data e ora attuale

	:return offers_win: list, contiene le offerte ancora aperte
	:return offers_no: list, contiene le offerte chiuse e non ufficializzate

	"""

	offers_win = dbf.db_select(
			table='offers',
			columns_in=['offer_id', 'offer_user', 'offer_player',
			            'offer_price', 'offer_datetime'],
			where='offer_status = "Winning"')

	offers_no = dbf.db_select(
			table='offers',
			columns_in=['offer_id', 'offer_user', 'offer_player',
			            'offer_price', 'offer_datetime'],
			where='offer_status = "Not Official"')

	# Se tra le offerte aperte ce n'è qualcuna per la quale sono già scadute
	# le 24 ore allora il suo status viene modificato a 'Not Official' ed
	# elimina eventuali autobids attivi per quel calciatore
	for of_id, tm, pl, pr, dt in offers_win:
		dt2 = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
		diff = dt_now - dt2
		if diff.days > 0:
			offers_no.append((of_id, tm, pl, pr, dt))
			dbf.db_update(
					table='offers',
					columns=['offer_status'],
					values=['Not Official'],
					where='offer_id = {}'.format(of_id))
			dbf.db_delete(
					table='autobids',
					where='autobid_player = "{}"'.format(pl))

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
	Imposta il valore dell'autobid per una data offerta.

	:param bot:
	:param update:
	:param args:list, input dell'user. Formato: giocatore, valore autobid
	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	message = 'Formato non corretto. Ex: /autobid petagna, 30'
	user = select_user(update)
	args = ''.join(args).split(',')

	# Controllo che il formato sia corretto
	if not args or len(args) != 2:
		return bot.send_message(chat_id=chat_id, text=message)

	pl, ab = args

	try:
		int(pl)
		return bot.send_message(chat_id=chat_id, text=message)
	except ValueError:
		pass

	try:
		int(ab)
	except ValueError:
		return bot.send_message(chat_id=chat_id, text=message)

	# aste_aperte = dbf.db_select(
	# 		table='offers',
	# 		columns_in=['offer_player'],
	# 		where='offer_status = "Winning"')
	# if not aste_aperte:
	# 	return bot.send_message(chat_id=chat_id,
	# 	                        text='Nessuna asta in corso')

	# Cerco nel db il calciatore corrispondente
	jpl = ef.jaccard_result(pl.upper(), dbf.db_select(
			table='players',
	        columns_in=['player_name'],
			where='player_status = "FREE"'), 3)
	if not jpl:
		return bot.send_message(
				chat_id=chat_id,
		        text=("Giocatore non trovato. Controllare che sia " +
		              "scritto correttamente."))

	# Squadra e ruoli
	tm, rl = dbf.db_select(
			table='players',
			columns_in=['player_team', 'player_roles'],
			where='player_name = "{}"'.format(jpl))[0]

	# Creo gli oggetti necessari per criptare il valore dell'autobid e li
	# inserisco nel db
	nonce, tag, value = dbf.encrypt_value(args[1])
	dbf.db_insert(
			table='autobids',
			columns=['autobid_user', 'autobid_player', 'autobid_nonce',
			         'autobid_tag', 'autobid_value'],
			values=[user, jpl, nonce, tag, value])

	message = ('\t\t\t\t<b>{}</b>  <i>{}  {}</i>'.format(jpl, tm, rl) +
	           '\n\nAutobid: {}\n\n\t\t\t\t/conferma_autobid'.format(ab))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=message)


def check_autobid(user, player_name, offer_id, datetm, last_off):

	"""
	Controlla se l'offerta supera o meno l'autobid impostato da un altro utente
	(qualora ce ne fosse uno) e gestisce il db di conseguenza.
	Utilizzata all'interno di conferma_offerta().

	:param user: str, fantasquadra offerente
	:param player_name: str, calciatore in questione
	:param offer_id: int, id dell'offerta presentata
	:param datetm: str, data e ora da formattare
	:param last_off: int, id dell'ultima offerta vincente per il calciatore

	:return: str o tuple a seconda della situazione

	"""

	# Seleziono tutti gli autobids già impostati da altri users per lo stesso
	# calcatore. Qualora non ce ne fossero, assegno valore nullo ad alcune
	# variabili in modo da gestire il codice successivo
	try:
		iid, ab_user, nonce, tag, encr_value = dbf.db_select(
				table='autobids',
				columns_in=['autobid_id', 'autobid_user', 'autobid_nonce',
				            'autobid_tag', 'autobid_value'],
				where='autobid_player = "{}"'.format(player_name))[0]
		last_ab = int(dbf.decrypt_value(nonce, tag, encr_value).decode())
	except IndexError:
		iid = 0
		last_ab = 0
		ab_user = ''

	offer = int(dbf.db_select(
			table='offers',
			columns_in=['offer_price'],
			where='offer_id = {}'.format(offer_id))[0])

	# Se l'offerta è inferiore all'autobid di un altro user: cancello l'offerta
	# dal db, aggiorno il valore dell'offerta dell'altro utente e, qualora
	# questo nuovo valore raggiunga il limite dell'autobid dell'altro user,
	# elimino tale autobid dal db
	if offer < last_ab:
		dbf.db_delete(table='offers', where='offer_id = {}'.format(offer_id))
		dbf.db_update(
				table='offers',
				columns=['offer_price', 'offer_datetime'],
				values=[offer + 1, datetm],
				where='offer_id = {}'.format(last_off))
		if offer + 1 == last_ab:
			dbf.db_delete(table='autobids',
			              where='autobid_id = {}'.format(iid))

		message1 = ("Offerta troppo bassa. Non hai superato" +
		            " l'autobid di {}.".format(ab_user))

		message2 = ('<i>{}</i> ha tentato un rilancio di '.format(user) +
		            '{} per <b>{}</b>.'.format(offer, player_name) +
		            '\n\n' + '_' * 30 + '\n\n\n' + crea_riepilogo(datetm))

		return message1, message2

	# Se invece l'offerta supera l'ultimo autobid allora cancello l'autobid dal
	# db ed aggiorno tutti gli altri parametri
	else:
		dbf.db_delete(table='autobids', where='autobid_id = {}'.format(iid))

		delete_not_conf_offers_by_others(player_name, user)

		dbf.db_update(
				table='offers',
				columns=['offer_datetime', 'offer_status'],
				values=[datetm, 'Winning'],
				where='offer_id = {}'.format(offer_id))

		dbf.db_update(
				table='offers',
				columns=['offer_status'],
				values=['Lost'],
				where='offer_id = {}'.format(last_off))

		message = crea_riepilogo(datetm)

		return message


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

	message = 'Formato errato. Es: /offro 5, padoin, cag.'

	if not args:
		return 'Inserire i dati. Es: /offro 5, padoin, cag.'

	args = ''.join(args).split(',')

	if len(args) != 3:
		return message
	else:
		offer, pl, team = args
		try:
			int(offer)
		except ValueError:
			return message

		try:
			int(pl)
			return message
		except ValueError:
			pass

		try:
			int(team)
			return message
		except ValueError:
			pass

		return offer, pl, team


def check_offer_value(offer_id, player, dt):

	"""
	Controlla se l'offerta è valida. Nell'ordine controlla:

		- In caso di rilancio, se è troppo tardi per farlo
		- In caso di rilancio, se l'offerta supera quella già presente
		- In caso di prima offerta, se il valore offerto è sufficiente

	Utilizzata all'interno di conferma_offerta().

	:param offer_id: int, id dell'offerta
	:param player: str, nome del giocatore
	:param dt: str, data ed ora attuali

	:return last_id: int, l'id dell'offerta più recente per questo giocatore.
					 0 nel caso non si tratti di rilancio ma di prima offerta.

	"""

	# Prendo dal db i dettagli dell'ultima offerta valida per questo
	# calciatore, qualora ci sia
	try:
		cond1 = 'offer_player = "{}" AND offer_status = "Winning"'.format(
				player)
		cond2 = 'offer_player = "{}" AND offer_status = "Not Official"'.format(
				player)

		last_id, last_user, last_offer, last_dt = dbf.db_select(
				table='offers',
				columns_in=['offer_id', 'offer_user',
				            'offer_price', 'offer_datetime'],
				where='{} OR {}'.format(cond1, cond2))[0]
	except IndexError:
		last_offer = 0
		last_user = ''
		last_id = 0
		last_dt = '2030-01-01 00:00:00'

	# Controllo che non siano passate le 24 ore. Se è troppo tardi, aggiorno
	# il db
	if too_late_to_offer(dt, last_dt):
		dbf.db_delete(table='offers', where='offer_id = {}'.format(offer_id))

		dbf.db_update(
				table='offers',
				columns=['offer_status'],
				values=['Not Official'],
				where='offer_id = {}'.format(last_id))

		dbf.db_update(
				table='players',
				columns=['player_status'],
				values=[last_user],
				where='player_name = "{}"'.format(player))

		return ('Troppo tardi, 24 ore scadute. ' +
		        '{} acquistato da {}'.format(player, last_user))

	# Se non è troppo tardi confronto l'offerta con l'ultimo rilancio e con la
	# quotazione, a seconda dei casi
	offer = dbf.db_select(
			table='offers',
			columns_in=['offer_price'],
			where='offer_id = {}'.format(offer_id))[0]

	price = dbf.db_select(
			table='players',
			columns_in=['player_price'],
			where='player_name = "{}"'.format(player))[0]

	if offer <= last_offer:
		dbf.db_delete(table='offers', where='offer_id = {}'.format(offer_id))
		return ('Offerta troppo bassa. ' +
				'Ultimo rilancio: {}, {}'.format(last_offer, last_user))

	elif offer < price:
		dbf.db_delete(table='offers', where='offer_id = {}'.format(offer_id))
		return 'Offerta troppo bassa. Quotazione: {}'.format(price)

	else:
		return last_id


def check_pago_format(args, user):

	"""
	Controlla il formato dell'input di pagamento e ritorna un messaggio
	esplicativo in caso di errore. Si assicura inoltre che l'offerta sia
	pagabile, ovvero che il giocatore in questione sia effettivamente dell'user
	e che siano trascorse le 24 ore necessarie.
	Utilizzata all'interno di pago().

	:param args: list, il pagamento dell'user
	:param user: str, nome della squadra fantacalcistica

	:return args: list, il pagamento dell'user
	:return offers_user: list, offerte non ufficializzate dell'user

	"""

	message = 'Formato errato. Es: /pago higuain, padoin, khedira, 18.'

	if not args:
		return 'Inserire i dati. Es: /pago higuain, padoin, khedira, 18.'

	args = ''.join(args).split(',')

	if len(args) < 2:
		return message
	else:

		try:
			int(args[0])
			return message
		except ValueError:
			pass

		# Prendo dal db tutte le offerte 'Not Official' dell'user. Nel caso non
		# ce ne siano mando un messaggio in chat
		offers_user = dbf.db_select(
				table='offers',
				columns_in=['offer_player'],
				where=('offer_user = "{}" AND '.format(user) +
				       'offer_status = "Not Official"'))
		if not len(offers_user):
			return ('Pagamento non valido. Possibili cause:\n\n' +
			        '\t\t\t- 24 ore non ancora trascorse;\n' +
			        '\t\t\t- Giocatore di proprietà di un altro utente;\n' +
			        '\t\t\t- Offerta inesistente')

		return args, offers_user


def conferma_autobid(bot, update):

	"""
	Elimina tutti i vecchi autobids non confermati dall'user e confronta il
	valore impostato con quello dell'ultima offerta valida. Se tutto ok,
	aggiorna il db.

	:param bot:
	:param update:
	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	# Tutti gli autobids dell'user
	autobids = dbf.db_select(
			table='autobids',
			columns_out=['autobid_user', 'autobid_status'],
			where=('autobid_user = "{}" '.format(user) +
			       'AND autobid_status IS NULL'))

	if not autobids:
		return bot.send_message(
				chat_id=chat_id, text='Nessun autobid da confermare')

	# Elimino tutti tranne l'ultimo in ordine di tempo
	old = autobids[:-1]
	for ab in old:
		dbf.db_delete(
				table='autobids',
				where='autobid_id = {}'.format(ab[0]))

	# Decripto il valore impostato e lo confronto con l'ultima offerta valida
	iid, pl, nonce, tag, encr_value = autobids[-1]
	ab_value = int(dbf.decrypt_value(nonce, tag, encr_value).decode())

	# Controllo se c'è già un'asta in corso per il calciatore
	try:
		last_offer = dbf.db_select(
				table='offers',
				columns_in=['offer_price'],
				where=('offer_player = "{}" AND '.format(pl) +
				       'offer_status = "Winning"'))[0]
	except IndexError:
		last_offer = 0

	# Se non c'è, gestisco la situazione in modo da presentare automaticamente
	# un'offerta a prezzo base oppure segnalare all'utente l'assenza di un'asta
	# attiva
	if not last_offer:
		message = prezzo_base_automatico(user, iid, pl, ab_value, active=True)

		if type(message) == tuple:
			return bot.send_message(chat_id=chat_id, text=message[1])
		else:
			return bot.send_message(parse_mode='HTML', chat_id=group_id,
			                        text=message)

	if ab_value <= last_offer:
		dbf.db_delete(table='autobids', where='autobid_id = {}'.format(iid))
		return bot.send_message(chat_id=chat_id,
		                        text=("Valore autobid troppo basso. " +
		                              "Impostare un valore superiore" +
		                              " all'attuale offerta vincente."))
	else:
		dbf.db_update(
				table='autobids',
				columns=['autobid_status'],
				values=['Confirmed'],
				where='autobid_id = {}'.format(iid))
		sf.logger.info('CONFERMA_AUTOBID - {} '.format(user) +
		            'imposta autobid per {}'.format(pl))
		return bot.send_message(chat_id=chat_id,
		                        text='Autobid impostato correttamente')


def conferma_offerta(bot, update):

	"""
	Conferma l'offerta effettuata (se valida) ed aggiorna il db di conseguenza.
	Infine manda un messaggio in chat con tutte le offerte aperte e chiuse.

	:param bot:
	:param update:

	:return: Nothing

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	# Controllo che ci siano offerte da confermare
	try:
		of_id, pl = select_offer_to_confirm(user)
	except TypeError:
		return bot.send_message(chat_id=chat_id,
								text='Nulla da confermare per {}'.format(user))

	# Controllo che il calciatore sia svincolato
	status = dbf.db_select(
					table='players',
					columns_in=['player_status'],
					where='player_name = "{}"'.format(pl))[0]
	if status != 'FREE':
		dbf.db_delete(table='offers', where='offer_id = {}'.format(of_id))
		return bot.send_message(chat_id=chat_id,
								text='Giocatore non svincolato ({}).'.
								format(status))

	# Controllo che l'offerta superi l'ultimo rilancio
	last_valid_offer = check_offer_value(of_id, pl, dt)
	if type(last_valid_offer) == str:
		return bot.send_message(chat_id=chat_id, text=last_valid_offer)

	# Controllo gli autobids
	result = check_autobid(user, pl, of_id, dt, last_valid_offer)
	if len(result) == 2:

		pvt_mess, group_mess = result

		bot.send_message(chat_id=chat_id, text=pvt_mess)

		return bot.send_message(parse_mode='HTML', chat_id=group_id,
		                        text=group_mess)

	else:

		return bot.send_message(parse_mode='HTML', chat_id=group_id,
		                        text=result)


def conferma_pagamento(bot, update):

	"""
	Conferma il pagamento di un'offerta ufficiale ed aggiorna il db di
	conseguenza. Innanzitutto controlla se i milioni offerti sono sufficienti,
	dopodichè controlla se si ha effettivamente il budget per completare il
	pagamento. Se l'offerta risulta valida a tutti gli effetti, verrà
	aggiornato il budget della squadra in questione, lo status dei calciotori
	coinvolti, la tabella "offers" e la tabella "pays".

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	# Controllo ci siano pagamenti da confermare e qualora ci fossero seleziono
	# l'ultimo in ordine di tempo e cancello tutti gli altri 'Not Confirmed'
	# dal db
	try:
		pay_id, pl, pr, mn = dbf.db_select(
				table='pays',
				columns_in=['pay_id', 'pay_player', 'pay_price', 'pay_money'],
				where='pay_user = "{}" AND pay_status = "Not Confirmed"'.
					format(user))[-1]
		dbf.db_delete(
				table='pays',
				where='pay_id != {} AND pay_player = "{}"'.format(pay_id, pl))
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
				table='pays',
				where='pay_user = "{}" AND pay_player = "{}"'.format(user, pl))
		return bot.send_message(chat_id=chat_id,
		                        text=('Offerta insufficiente.\n' +
		                              'Milioni mancanti: {}'.format(
				                              pr - temp_bud)))

	# Sommo al budget della fantasquadra il prezzo dei giocatori utilizzati
	# nel pagamento, se presenti, e che saranno quindi ceduti
	budget = dbf.db_select(
			table='budgets',
			columns_in=['budget_value'],
			where='budget_team = "{}"'.format(user))[0]

	for i in mn:
		try:
			int(i)
		except ValueError:
			budget += dbf.db_select(
					table='players',
					columns_in=['player_price'],
					where='player_name = "{}"'.format(i.split(' (')[0]))[0]

	# Qualora l'offerta sia valida, aggiorno varie voci nel db sia del
	# calciatore acquistato che di quelli ceduti, se presenti
	if budget < pr:
		dbf.db_delete(
				table='pays',
				where='pay_user = "{}" AND pay_player = "{}"'.format(user, pl))
		return bot.send_message(chat_id=chat_id,
		                        text='Budget insufficiente')
	else:
		dbf.db_update(
				table='budgets',
				columns=['budget_value'],
				values=[int(budget - pr)],
				where='budget_team = "{}"'.format(user))

		dbf.db_update(
				table='players',
				columns=['player_status'],
				values=[user],
				where='player_name = "{}"'.format(pl))

		dbf.db_update(
				table='offers',
				columns=['offer_status'],
				values=['Official'],
				where='offer_player = "{}" AND offer_status = "Not Official"'.
					format(pl))

		dbf.db_update(
				table='pays',
				columns=['pay_status'],
				values=['Confirmed'],
				where='pay_player = "{}"'.format(pl))

		for i in mn:
			try:
				int(i)
			except ValueError:
				dbf.db_update(
						table='players',
						columns=['player_status'],
						values=['FREE'],
						where='player_name = "{}"'.format(i.split(' (')[0]))

	message = ('<i>{}</i> ha ufficializzato '.format(user) +
	           '<b>{}</b> a {}.'.format(pl, pr) +
	           '\n\nPagamento: {}'.format(', '.join(mn)))

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	bot.send_message(parse_mode='HTML', chat_id=group_id,
	                 text=(message + '\n\n' + '_'*30 + '\n\n\n' +
	                       crea_riepilogo(dt)))

	# mn2 = []
	# for i in mn:
	# 	try:
	# 		int(i)
	# 	except ValueError:
	# 		mn2.append(i)
	#
	# browser = sf.login()
	# if mn2:
	# 	cessioni = [el.split(' (')[0] for el in mn2]
	# 	sf.aggiorna_cessioni(browser, user, cessioni)
	# sf.aggiorna_acquisti(browser, user, pl)


def crea_riepilogo(dt_now):

	"""
	Mette insieme i vari messaggi di riepilogo delle offerte:

		- Aperte
		- Concluse ma non ufficializzate
		- Ufficializzate

	Utilizzata dentro conferma_offerta() e riepilogo().

	:param dt_now: str, data e ora da trasformare in datetime

	:return: messaggio in chat

	"""

	dt_now = datetime.strptime(dt_now, '%Y-%m-%d %H:%M:%S')

	message1 = 'Aste APERTE, Tempo Rimanente:\n'
	message2 = 'Aste CONCLUSE, NON Ufficializzate:\n'

	offers_win, offers_no = aggiorna_offerte_chiuse(dt_now)

	message1 = message_with_offers(offers_win, 1, dt_now, message1)
	message2 = message_with_offers(offers_no, 2, dt_now, message2)

	message = message1 + '\n\n\n\n' + message2

	return message


def delete_not_conf_offers_by_others(player_name, user):

	"""
	Elimina dal db le offerte di altri users per lo stesso giocatore che non
	sono state confermate.
	Utilizzata all'interno di conferma_offerta().

	:param player_name: str, nome del giocatore
	:param user: str, fantasquadra

	:return: Nothing

	"""

	old_ids = dbf.db_select(
			table='offers',
			columns_in=['offer_id'],
			where='offer_player = "{}"'.format(player_name) +
				  'AND offer_status IS NULL AND ' +
				  'offer_user != "{}"'.format(user))

	for old_id in old_ids:
		dbf.db_delete(table='offers', where='offer_id = {}'.format(old_id))


def delete_not_conf_offers_by_user(user):

	"""
	Elimina dal db le offerte dell'user che non sono state confermate.
	Utilizzata all'interno di check_autobid().

	:param user: str, fantasquadra

	:return: Nothing

	"""

	try:
		old_id = dbf.db_select(
				table='offers',
				columns_in=['offer_id'],
				where='offer_user = "{}" '.format(user) +
					  'AND offer_status IS NULL')[0]

		dbf.db_delete(table='offers', where='offer_id = {}'.format(old_id))

	except IndexError:
		pass


def info(bot, update):

	"""
	Invia in chat le info.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""
	chat_id = update.message.chat_id
	if update.message.chat_id == group_id:
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

	return bot.send_message(chat_id=chat_id, text=message)


def message_with_offers(list_of_offers, shift, dt_now, msg):

	"""
	Crea il messaggio di riepilogo delle offerte.
	Utilizzata dentro crea_riepilogo().

	:param list_of_offers: list, ogni tuple è un'offerta
	:param shift: int, per calcolare lo shift in giorni e il tempo rimanente
	:param dt_now: datetime, data e ora attuali
	:param msg: str, messaggio da completare

	:return msg: str, messaggio finale

	"""

	for _, tm, pl, pr, dt in list_of_offers:
		team, roles = dbf.db_select(
				table='players',
				columns_in=['player_team', 'player_roles'],
				where='player_name = "{}"'.format(pl))[0]
		dt_plus = dt + timedelta(days=shift)
		diff = (dt_plus - dt_now).total_seconds()
		hh = diff // 3600
		mm = (diff % 3600) // 60

		msg += ('\n\t\t- <b>{}</b> ({}) {}:'.format(pl, team, roles) +
		        ' {}, <i>{}</i>  '.format(pr, tm) +
				' <b>{}h:{}m</b>'.format(int(hh), int(mm)))

	return msg


def message_with_payment(bot, update, user, user_input, offers_user):

	"""
	Crea il messaggio di riepilogo del pagamento.
	Utilizzato all'interno della funzione pago().

	:param bot:
	:param update:
	:param user: str, nome della fantasquadra
	:param user_input: list, [giocatore da pagare, metodo di pagamento]
	:param offers_user: list, tutte le offerte dell'user in stato Not Official

	:return money_db: list, user_input dopo la correzioni dei nomi
	:return message: str, messaggio di riepilogo

	"""

	chat_id = update.message.chat_id

	# Nel pagamento proposto dall'user separo i calciatori dai soldi
	pls = []
	money = 0
	for i in user_input:
		try:
			money = int(i)
		except ValueError:
			pls.append(i)

	# Tra i calciatori separo quello da acquistare da quelli da svincolare
	acquisto, pagamento = pls[0], pls[1:]

	# Gestisco prima tutta la parte relativa all'acquisto
	pl = ef.jaccard_result(acquisto.upper(), offers_user, 3)
	if not pl:
		return bot.send_message(chat_id=chat_id,
		                        text=jac_message)

	off_id, price = dbf.db_select(
			table='offers',
			columns_in=['offer_id', 'offer_price'],
			where='offer_player = "{}"'.format(pl))[-1]

	dbf.db_insert(
			table='pays',
			columns=['pay_user', 'pay_offer',
			         'pay_player', 'pay_price'],
			values=[user, off_id, pl, price])

	team, roles = dbf.db_select(
			table='players',
			columns_in=['player_team', 'player_roles'],
			where='player_name = "{}"'.format(pl))[0]

	message = ('<i>{}</i> ufficializza:\n\n\t\t\t\t\t\t'.format(user) +
	           '<b>{}</b> <i>({})   {}</i>\n\n'.format(pl, team,
	                                                   roles) +
	           'Prezzo: <b>{}</b>.\n\nPagamento:\n'.format(price))

	# E poi quella relativa alle varie cessioni, se presenti
	rosa = dbf.db_select(
			table='players',
			columns_in=['player_name'],
			where='player_status = "{}"'.format(user))

	for i, pl in pagamento:
		pl2 = ef.jaccard_result(pl.upper(), rosa, 3)
		if not pl2:
			return bot.send_message(chat_id=chat_id,
			                        text=jac_message)

		tm, rls, pr = dbf.db_select(
				table='players',
				columns_in=['player_team', 'player_roles', 'player_price'],
				where='player_name = "{}"'.format(pl2))[0]

		pagamento[i] = (pl2, tm, rls, pr)

	# Formatto alcuni parametri per poi inviarli come messaggio in chat
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

	return money_db, message + '\n\n/conferma_pagamento'


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
	if update.message.chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	# Controllo che il formato sia giusto
	try:
		offer, pl, team = check_offer_format(args)
	except ValueError:
		message = check_offer_format(args)
		return bot.send_message(chat_id=chat_id, text=message)

	delete_not_conf_offers_by_user(user)

	# Cerco nel db la squadra corrispondente all'input dell'user
	j_tm = ef.jaccard_result(team[:3].upper(),
	                         dbf.db_select(table='players',
	                                       columns_in=['player_team']), 3)
	if not j_tm:
		return bot.send_message(chat_id=chat_id, text=jac_message)

	# Seleziono i calciatori della squadra scelta
	pls = dbf.db_select(
					table='players',
					columns_in=['player_name'],
					where='player_team = "{}"'.format(j_tm))

	# Cerco il calciatore corrispondente all'input dell'user ed aggiorno il db
	pl = ef.jaccard_result(pl.upper(), pls, 3)
	if not pl:
		return bot.send_message(chat_id=chat_id, text=jac_message)

	pl_id = int(dbf.db_select(
			table='players',
			columns_in=['player_id'],
			where='player_name = "{}"'.format(pl))[0])

	team, roles, price = dbf.db_select(
			table='players',
			columns_in=['player_team', 'player_roles', 'player_price'],
			where='player_name = "{}"'.format(pl))[0]

	dbf.db_insert(
			table='offers',
			columns=['offer_user', 'offer_player', 'offer_player_id',
			         'offer_price'],
			values=[user, pl, pl_id, offer])

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
							text='<i>{}</i> offre <b>{}</b> per:\n\n\t\t'.
							format(user, offer) +
							     '<b>{}   ({})   {}</b>'.
							format(pl, team, roles) +
							'\n\n/conferma_offerta')


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
			columns_in=['player_name', 'player_team', 'player_roles'],
			where='player_status = "{}"'.format(user))

	rosa = [(el[0], el[1], el[2], roles_dict[el[2].split(';')[0]]) for
	        el in rosa]
	rosa.sort(key=lambda x: x[3])

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
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')

	_, _ = aggiorna_offerte_chiuse(dt)

	# Controllo che il formato sia corretto
	try:
		args, offers_user = check_pago_format(args, user)
	except ValueError:
		return bot.send_message(chat_id=chat_id,
		                        text=check_pago_format(args, user))

	money_db, message = message_with_payment(bot, update, user, args,
	                                         offers_user)

	dbf.db_update(
			table='pays',
			columns=['pay_money', 'pay_status'],
			values=[money_db, 'Not Confirmed'],
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
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	if len(args) != 2:
		return bot.send_message(chat_id=chat_id,
		                        text=('Formato non corretto.\n' +
		                        'Ex: /prezzo higuain, milan'))

	pl, tm = ''.join(args).split(',')

	tm = ef.jaccard_result(
			tm.upper(), dbf.db_select(table='players',
			                          columns_in=['player_team']), 3)
	if not tm:
		return bot.send_message(chat_id=chat_id,
		                        text=jac_message)

	pl = ef.jaccard_result(pl.upper(),
	                       dbf.db_select(
			                       table='players',
			                       columns_in=['player_name'],
	                               where='player_team = "{}"'.format(tm)), 3)
	if not pl:
		return bot.send_message(chat_id=chat_id,
		                        text=jac_message)

	rl, pr, st = dbf.db_select(
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
	Presenta on'offerta a prezzo base o comunica la mancanza di un'asta attiva.
	Utilizzata all'interno di conferma_autobid(). L'oggetto del return può
	essere un tuple o una str in modo da distinguere il messaggio da inviare
	in chat privata e quello da inviare nel gruppo ufficiale.

	:param user: str, fantasquadra
	:param ab_id: int, id dell'autobid
	:param player_name: str, nome del calciatore
	:param autobid_value: int, valore autobid
	:param active: bool

	:return: tuple o str a seconda dei casi

	"""

	if active:

		dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

		pl_id, pr_base = dbf.db_select(
				table='players',
				columns_in=['player_id', 'player_price'],
				where='player_name = "{}"'.format(player_name))[0]

		if autobid_value < pr_base:
			dbf.db_delete(
					table='autobids',
					where='autobid_id = {}'.format(ab_id))

			return (False, 'Valore autobid troppo basso. ' +
			        'Prezzo base: {}'.format(pr_base))

		dbf.db_insert(
				table='offers',
				columns=['offer_user', 'offer_player', 'offer_player_id',
				         'offer_price', 'offer_datetime', 'offer_status'],
				values=[user, player_name, pl_id, pr_base, dt, 'Winning'])

		dbf.db_update(
				table='autobids',
				columns=['autobid_status'],
				values=['Confirmed'],
				where='autobid_id = {}'.format(ab_id))
		sf.logger.info('PREZZO_BASE_AUTOMATICO - {} '.format(user) +
		               'offre prezzo base ed imposta autobid ' +
		               'per {}'.format(player_name))

		return crea_riepilogo(dt)

	else:
		dbf.db_delete(
				table='autobids',
				where='autobid_id = {}'.format(ab_id))

		return False, 'Nessuna asta trovata per il calciatore scelto.'


def print_rosa(bot, update):

	"""
	Invia in chat un messaggio con la rosa dell'user, il numero di giocatori ed
	il budget disponibile.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	message = '<i>{}</i> :\n'.format(user)

	rosa = order_by_role(user)

	for pl, tm, rl in rosa:
		message += '\n\t\t\t<b>{}</b> ({})     {}'.format(pl, tm, rl)

	budget = dbf.db_select(
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
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=crea_riepilogo(dt))


def select_offer_to_confirm(user):

	"""
	Seleziona l'offerta che l'utente deve confermare, se corretta.
	Ritorna un messaggio esplicativo in caso di assenza di offerte da
	confermare.
	Utilizzata all'interno di conferma_offerta().

	:param user: str, squadra di uno dei partecipanti

	:return of_id: int, id dell'offerta
	:return pl: str, nome del giocatore in questione

	"""

	try:
		of_id, pl = dbf.db_select(
				table='offers',
				columns_in=['offer_id', 'offer_player'],
				where='offer_user = "{}" AND offer_datetime IS NULL'.
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

	try:
		user = dbf.db_select(
				table='teams',
				columns_in=['team_name'],
				where='team_member = "{}"'.format(
						update.message.from_user.first_name))[0]
		return user

	except IndexError:
		return False


def too_late_to_offer(time_now, time_before):

	"""
	Controlla se si è ancora in tempo per rilanciare un'offerta.
	Utilizzata all'interno di check_offer_value().

	:param time_now: str, data e ora attuali da formattare in datetime
	:param time_before: str, data e ora precedenti da formattare in datetime

	:return: bool, True se troppo tardi altrimenti False

	"""

	time_now = datetime.strptime(time_now, '%Y-%m-%d %H:%M:%S')
	time_before = datetime.strptime(time_before, '%Y-%m-%d %H:%M:%S')

	diff = time_now - time_before

	if diff.days > 0:
		return True
	else:
		return False


def ufficiali(bot, update):

	"""
	Crea il messaggio con le offerte già ufficializzate.

	:return message: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == group_id:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	message = 'Ufficializzazioni:\n'

	uffic = dbf.db_select(
			table='offers',
			columns_in=['offer_id', 'offer_user',
			            'offer_player', 'offer_price'],
			where='offer_status = "Official"')

	for off_id, user, pl, pr in uffic:

		tm = dbf.db_select(
				table='players',
				columns_in=['player_team'],
				where='player_name = "{}"'.format(pl))[0]

		pagamento = dbf.db_select(
				table='pays',
				columns_in=['pay_money'],
				where='pay_offer = {}'.format(off_id))[0]

		message += ('\n\t\t\t\t- <i>{}</i> '.format(user) +
		            'acquista <b>{}</b> ({}) a {}. '.format(pl, tm, pr) +
		            'Pagamento: <i>{}</i>.'.format(pagamento))

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


# aaa_handler = CommandHandler('aaa', aaa)
autobid_handler = CommandHandler('autobid', autobid, pass_args=True)
conferma_autobid_handler = CommandHandler('conferma_autobid', conferma_autobid)
conferma_offerta_handler = CommandHandler('conferma_offerta', conferma_offerta)
conferma_pagamento_handler = CommandHandler('conferma_pagamento',
                                            conferma_pagamento)
info_handler = CommandHandler('info', info)
offro_handler = CommandHandler('offro', offro, pass_args=True)
pago_handler = CommandHandler('pago', pago, pass_args=True)
prezzo_handler = CommandHandler('prezzo', prezzo, pass_args=True)
riepilogo_handler = CommandHandler('riepilogo', riepilogo)
rosa_handler = CommandHandler('rosa', print_rosa)
ufficiali_handler = CommandHandler('ufficiali', ufficiali)

# dispatcher.add_handler(aaa_handler)
dispatcher.add_handler(autobid_handler)
dispatcher.add_handler(conferma_autobid_handler)
dispatcher.add_handler(conferma_offerta_handler)
dispatcher.add_handler(conferma_pagamento_handler)
dispatcher.add_handler(info_handler)
dispatcher.add_handler(offro_handler)
dispatcher.add_handler(pago_handler)
dispatcher.add_handler(prezzo_handler)
dispatcher.add_handler(riepilogo_handler)
dispatcher.add_handler(rosa_handler)
dispatcher.add_handler(ufficiali_handler)

updater.start_polling()
# logger = log.set_logging()
updater.idle()
