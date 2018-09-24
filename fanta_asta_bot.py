from datetime import datetime, timedelta
import db_functions as dbf
import extra_functions as ef
from telegram.ext import Updater, CommandHandler


f = open('token.txt', 'r')
updater = Updater(token=f.readline())
f.close()
dispatcher = updater.dispatcher
BLOCK = False


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

	offers_win = [(el[0], el[1], el[2], el[3],
	               datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
	              offers_win if el not in offers_no]

	offers_no = [(el[0], el[1], el[2], el[3],
	              datetime.strptime(el[4], '%Y-%m-%d %H:%M:%S')) for el in
	             offers_no]

	return offers_win, offers_no


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

	offer = dbf.db_select(
			table='offers',
			columns_in=['offer_price'],
			where='offer_id = {}'.format(offer_id))[0]

	price = dbf.db_select(
			table='players',
			columns_in=['player_price'],
			where='player_name = "{}"'.format(player))[0]

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


def conferma_offerta(bot, update):

	"""
	Conferma l'offerta effettuata (se valida) ed aggiorna il db di conseguenza.
	Infine manda un messaggio in chat con tutte le offerte aperte e chiuse.

	:param bot:
	:param update:

	:return: Nothing

	"""

	if BLOCK:
		if update.message.chat_id != -318148079:
			return bot.send_message(chat_id=update.message.chat_id,
			                        text='Utilizza il gruppo ufficiale')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	try:
		of_id, pl = select_offer_to_confirm(user)
	except ValueError:
		return bot.send_message(chat_id=update.message.chat_id,
								text=select_offer_to_confirm(user))

	status = dbf.db_select(
					table='players',
					columns_in=['player_status'],
					where='player_name = "{}"'.format(pl))[0]
	if status != 'FREE':
		dbf.db_delete(table='offers', where='offer_id = {}'.format(of_id))
		return bot.send_message(chat_id=update.message.chat_id,
								text='Giocatore non svincolato ({}).'.
								format(status))

	last_valid_offer = check_offer_value(of_id, pl, dt)
	if type(last_valid_offer) == str:
		return bot.send_message(chat_id=update.message.chat_id,
								text=last_valid_offer)

	pl_id = dbf.db_select(
					table='players',
					columns_in=['player_id'],
					where='player_name = "{}"'.format(pl))[0]

	delete_not_conf_offers_by_others(pl_id, user)

	dbf.db_update(
			table='offers',
			columns=['offer_datetime', 'offer_status'],
			values=[dt, 'Winning'],
			where='offer_id = {}'.format(of_id))

	dbf.db_update(
			table='offers',
			columns=['offer_status'],
			values=['Lost'],
			where='offer_id = {}'.format(last_valid_offer))

	crea_riepilogo(bot, update, dt)


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

	if BLOCK:
		if update.message.chat_id != -318148079:
			return bot.send_message(chat_id=update.message.chat_id,
			                        text='Utilizza il gruppo ufficiale')

	user = select_user(update)

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
		return bot.send_message(chat_id=update.message.chat_id,
		                        text='Nulla da confermare per {}'.format(user))

	budget = dbf.db_select(
			table='budgets',
			columns_in=['budget_value'],
			where='budget_team = "{}"'.format(user))[0]

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
		return bot.send_message(chat_id=update.message.chat_id,
		                        text=('Offerta insufficiente.\n' +
		                              'Milioni mancanti: {}'.format(
				                              pr - temp_bud)))

	for i in mn:
		try:
			int(i)
		except ValueError:
			budget += dbf.db_select(
					table='players',
					columns_in=['player_price'],
					where='player_name = "{}"'.format(i.split(' (')[0]))[0]

	if budget < pr:
		dbf.db_delete(
				table='pays',
				where='pay_user = "{}" AND pay_player = "{}"'.format(user, pl))
		return bot.send_message(chat_id=update.message.chat_id,
		                        text='Budget insufficiente')
	else:
		dbf.db_update(
				table='budgets',
				columns=['budget_value'],
				values=[budget - pr],
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

	return bot.send_message(chat_id=update.message.chat_id,
		                    text=('Rosa {} aggiornata.\n'.format(user) +
		                          'Budget aggiornato: {}'.format(budget - pr)))


def crea_riepilogo(bot, update, dt_now):

	"""
	Mette insieme i vari messaggi di riepilogo delle offerte:

		- Aperte
		- Concluse ma non ufficializzate
		- Ufficializzate

	Utilizzata dentro conferma_offerta() e riepilogo().

	:param bot:
	:param update:
	:param dt_now: str, data e ora da trasformare in datetime

	:return: messaggio in chat

	"""

	dt_now = datetime.strptime(dt_now, '%Y-%m-%d %H:%M:%S')

	message1 = 'Aste APERTE, Tempo Rimanente:\n'
	message2 = 'Aste CONCLUSE, NON Ufficializzate:\n'
	message3 = ufficializzazioni()

	offers_win, offers_no = aggiorna_offerte_chiuse(dt_now)

	message1 = message_with_offers(offers_win, 1, dt_now, message1)
	message2 = message_with_offers(offers_no, 2, dt_now, message2)

	return bot.send_message(parse_mode='HTML', chat_id=update.message.chat_id,
	                        text=(message1 + '\n\n\n\n' + message2 +
	                             '\n\n\n\n' + message3))


def delete_not_conf_offers_by_others(player_id, user):

	"""
	Elimina dal db le offerte di altri users per lo stesso giocatore che non
	sono state confermate.
	Utilizzata all'interno di conferma_offerta().

	:param player_id: int, id del giocatore
	:param user: str, fantasquadra

	:return: Nothing

	"""

	old_ids = dbf.db_select(
			table='offers',
			columns_in=['offer_id'],
			where='offer_player_id = {} '.format(player_id) +
				  'AND offer_status IS NULL AND ' +
				  'offer_user != "{}"'.format(user))

	for old_id in old_ids:
		dbf.db_delete(table='offers', where='offer_id = {}'.format(old_id))


def delete_not_conf_offers_by_user(user):

	"""
	Elimina dal db le offerte dell'user che non sono state confermate.
	Utilizzata all'interno di conferma_offerta().

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


def message_with_payment(user, user_input, offers_user):

	"""
	Crea il messaggio di riepilogo del pagamento.
	Utilizzato all'interno della funzione pago().

	:param user: str, nome della fantasquadra
	:param user_input: list, [giocatore da pagare, metodo di pagamento]
	:param offers_user: list, tutte le offerte dell'user in stato Not Official

	:return money_db: list, user_input dopo la correzioni dei nomi
	:return message: str, messaggio di riepilogo

	"""

	rosa = dbf.db_select(
			table='players',
			columns_in=['player_name'],
			where='player_status = "{}"'.format(user))

	pls = []
	money = 0
	message = ''

	for i in user_input:
		try:
			money = int(i)
		except ValueError:
			pls.append(i)

	new_pls = []
	for i, pl in enumerate(pls):
		if not i:
			pl2 = ef.jaccard_result(pl.upper(), offers_user, 3)

			off_id, price = dbf.db_select(
					table='offers',
					columns_in=['offer_id', 'offer_price'],
					where='offer_player = "{}"'.format(pl2))[-1]

			dbf.db_insert(
					table='pays',
					columns=['pay_user', 'pay_offer',
					         'pay_player', 'pay_price'],
					values=[user, off_id, pl2, price])

			team, roles = dbf.db_select(
					table='players',
					columns_in=['player_team', 'player_roles'],
					where='player_name = "{}"'.format(pl2))[0]

			message = ('<i>{}</i> ufficializza:\n\n\t\t\t\t\t\t'.format(user) +
			           '<b>{}</b> <i>({})   {}</i>\n\n'.format(pl2, team,
			                                                   roles) +
			           'Prezzo: <b>{}</b>.\n\nPagamento:\n'.format(price))

		else:
			pl2 = ef.jaccard_result(pl.upper(), rosa, 3)
			tm, rls, pr = dbf.db_select(
					table='players',
					columns_in=['player_team', 'player_roles', 'player_price'],
					where='player_name = "{}"'.format(pl2))[0]

			new_pls.append((pl2, tm, rls, pr))

	money_db = ', '.join(['{} ({}: {})'.format(el[0], el[1], el[3]) for el in
	                      new_pls])
	if money and len(new_pls):
		money_db += ', {}'.format(money)
	elif money:
		money_db += '{}'.format(money)

	for pl, tm, rl, pr in new_pls:
		message += '\n\t\t- <b>{}</b> <i>({})   {}</i>   {}'.format(pl, tm,
		                                                            rl, pr)
	if money:
		message += '\n\t\t- <b>{}</b>'.format(money)

	return money_db, message + '\n\n/conferma_pagamento'


def info(bot, update):

	"""
	Invia in chat le info.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	g = open('info.txt', 'r')
	content = g.readlines()
	g.close()

	message = ''
	for row in content:
		row = row.replace('xx\n', ' ')
		message += row

	return bot.send_message(chat_id=update.message.chat_id, text=message)


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

	if BLOCK:
		if update.message.chat_id != -318148079:
			return bot.send_message(chat_id=update.message.chat_id,
			                        text='Utilizza il gruppo ufficiale')

	user = select_user(update)

	try:
		offer, pl, team = check_offer_format(args)
	except ValueError:
		message = check_offer_format(args)
		return bot.send_message(chat_id=update.message.chat_id, text=message)

	delete_not_conf_offers_by_user(user)

	all_teams = list(set(dbf.db_select(
					table='players',
					columns_in=['player_team'])))
	j_tm = ef.jaccard_result(team[:3].upper(), all_teams, 3)
	j_pl = dbf.db_select(
					table='players',
					columns_in=['player_name'],
					where='player_team = "{}"'.format(j_tm))
	if not len(j_pl):
		return bot.send_message(chat_id=update.message.chat_id,
		                        text='Squadra inesistente')

	pl = ef.jaccard_result(pl.upper(), j_pl, 3)
	pl_id = dbf.db_select(
			table='players',
			columns_in=['player_id'],
			where='player_name = "{}"'.format(pl))[0]

	team, roles, price = dbf.db_select(
			table='players',
			columns_in=['player_team', 'player_roles', 'player_price'],
			where='player_name = "{}"'.format(pl))[0]

	dbf.db_insert(
			table='offers',
			columns=['offer_user', 'offer_player', 'offer_player_id',
			         'offer_price'],
			values=[user, pl, pl_id, offer])

	return bot.send_message(parse_mode='HTML',
	                        chat_id=update.message.chat_id,
							text='<i>{}</i> offre <b>{}</b> per:\n\n\t\t'.
							format(user, offer) +
							     '<b>{}   ({})   {}</b>'.
							format(pl, team, roles) +
							'\n\n/conferma_offerta')


def pago(bot, update, args):

	"""
	Aggiorna la tabella "pays" del db con lo status di "Not Confirmed".

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	if BLOCK:
		if update.message.chat_id != -318148079:
			return bot.send_message(chat_id=update.message.chat_id,
			                        text='Utilizza il gruppo ufficiale')

	user = select_user(update)

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')

	_, _ = aggiorna_offerte_chiuse(dt)

	try:
		args, offers_user = check_pago_format(args, user)
	except ValueError:
		return bot.send_message(chat_id=update.message.chat_id,
		                        text=check_pago_format(args, user))

	money_db, message = message_with_payment(user, args, offers_user)

	dbf.db_update(
			table='pays',
			columns=['pay_money', 'pay_status'],
			values=[money_db, 'Not Confirmed'],
			where='pay_user = "{}" AND pay_status IS NULL'.format(user))

	return bot.send_message(parse_mode='HTML', chat_id=update.message.chat_id,
	                        text=message)


def print_rosa(bot, update):

	"""
	Invia in chat un messaggio con la rosa dell'user, il numero di giocatori ed
	il budget disponibile.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	user = select_user(update)

	message = '<i>{}</i> :\n'.format(user)

	roles_dict = {'Por': 1, 'Dc': 2, 'Dd': 2, 'Ds': 2, 'E': 4, 'M': 4, 'C': 5,
	              'W': 6, 'T': 6, 'A': 7, 'Pc': 7}

	rosa1 = dbf.db_select(
			table='players',
			columns_in=['player_name', 'player_team', 'player_roles'],
			where='player_status = "{}"'.format(user))

	rosa2 = [(el[0], el[1], el[2], roles_dict[el[2].split(';')[0]]) for
	         el in rosa1]
	rosa2.sort(key=lambda x: x[3])

	rosa3 = [el[:-1] for el in rosa2]

	for pl, tm, rl in rosa3:
		message += '\n\t\t\t<b>{}</b> ({})     {}'.format(pl, tm, rl)

	budget = dbf.db_select(
			table='budgets',
			columns_in=['budget_value'],
			where='budget_team = "{}"'.format(user))[0]

	message += ('\n\nNumero di giocatori: <b>{}</b>\n'.format(len(rosa3)) +
	            'Milioni disponibili: <b>{}</b>'.format(budget))

	return bot.send_message(parse_mode='HTML', chat_id=update.message.chat_id,
	                        text=message)


def riepilogo(bot, update):

	"""
	Invia in chat il riepilogo delle offerte aperte, chiuse ma non ancora
	ufficializzate e quelle già ufficializzate.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	return crea_riepilogo(bot, update, dt)


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
		return 'Nulla da confermare per {}'.format(user)


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


def start(bot, update):

	bot.send_message(chat_id=update.message.chat_id, text="Iannelli suca")


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


def ufficializzazioni():

	"""
	Crea il messaggio con le offerte già ufficializzate.
	Utilizzata all'interno di crea_riepilogo().

	:return message: str, messaggio

	"""

	message = 'Ufficializzazioni:\n'

	ufficiali = dbf.db_select(
			table='offers',
			columns_in=['offer_id', 'offer_user',
			            'offer_player', 'offer_price'],
			where='offer_status = "Official"')

	for off_id, user, pl, pr in ufficiali:

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

	return message


aaa_handler = CommandHandler('aaa', aaa)
conferma_offerta_handler = CommandHandler('conferma_offerta', conferma_offerta)
conferma_pagamento_handler = CommandHandler('conferma_pagamento',
                                            conferma_pagamento)
offro_handler = CommandHandler('offro', offro, pass_args=True)
pago_handler = CommandHandler('pago', pago, pass_args=True)
info_handler = CommandHandler('info', info)
riepilogo_handler = CommandHandler('riepilogo', riepilogo)
rosa_handler = CommandHandler('rosa', print_rosa)

dispatcher.add_handler(aaa_handler)
dispatcher.add_handler(conferma_offerta_handler)
dispatcher.add_handler(conferma_pagamento_handler)
dispatcher.add_handler(offro_handler)
dispatcher.add_handler(info_handler)
dispatcher.add_handler(pago_handler)
dispatcher.add_handler(riepilogo_handler)
dispatcher.add_handler(rosa_handler)

updater.start_polling()
updater.idle()
