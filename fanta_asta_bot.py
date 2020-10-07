from datetime import datetime
import config as cfg
import utils as utl
import db_functions as dbf
import extra_functions as ef
import selenium_function as sf
from telegram.ext import Updater, CommandHandler


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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text=('Grazie per avercelo fatto sapere ' +
		                              'ma devi mandarlo in chat privata.'))

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	utl.aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutti gli autobid precedenti non confermati dall'utente
	dbf.db_delete(
			table='autobids',
			where=f'autobid_user = "{user}" AND autobid_status IS NULL')

	result = utl.check_autobid_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		jpl, ab = result

	# Squadra e ruoli
	tm, rl = dbf.db_select(
			table='players',
			columns=['player_team', 'player_roles'],
			where=f'player_name = "{jpl}"')[0]

	# Creo gli oggetti necessari per criptare il valore dell'autobid e li
	# inserisco nel db
	nonce, tag, value = dbf.encrypt_value(ab)
	dbf.db_insert(
			table='autobids',
			columns=['autobid_user', 'autobid_player', 'autobid_nonce',
			         'autobid_tag', 'autobid_value'],
			values=[user, jpl, nonce, tag, value])

	message = (f'\t\t\t\t<b>{jpl}</b>  <i>{tm}  {rl}</i>' +
	           f'\n\nAutobid: {ab}\n\n\t\t\t\t/confermo_autobid')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=message)


def confermo_autobid(bot, update):

	"""
	Confronta il valore impostato con quello dell'ultima offerta valida. Se
	tutto ok, aggiorna il db.

	:param bot:
	:param update:
	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if cfg.BLOCK:
		group_id = cfg.POLPS_ID
	else:
		group_id = cfg.FANTA_ID

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	utl.aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Decripto il valore impostato
	new_id, pl, nonce, tag, encr_value = dbf.db_select(
			table='autobids',
			columns=['autobid_id', 'autobid_player', 'autobid_nonce',
			         'autobid_tag', 'autobid_value'],
			where=f'autobid_user = "{user}" AND autobid_status IS NULL')[0]
	new_ab = int(dbf.decrypt_value(nonce, tag, encr_value).decode())

	# Esamino tutti i possibili casi
	private, group = utl.check_autobid_value(user, pl, new_id, new_ab)

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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	ab_to_delete = dbf.db_select(
			table='elimina',
			columns=['elimina_ab'],
			where=f'elimina_user = "{user}"')
	if not ab_to_delete:
		return bot.send_message(chat_id=chat_id,
		                        text='Non hai autobid da eliminare.')

	dbf.db_delete(
			table='autobids',
	        where=f'autobid_id = {ab_to_delete[0]}')

	dbf.db_delete(
			table='elimina',
	        where=f'elimina_ab = {ab_to_delete[0]}')

	message = 'Autobid eliminato' + cfg.SEPAR + utl.crea_riepilogo_autobid(user)

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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if cfg.BLOCK:
		group_id = cfg.POLPS_ID
	else:
		group_id = cfg.FANTA_ID

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	utl.aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Controllo che ci siano offerte da confermare
	try:
		of_id, pl = utl.select_offer_to_confirm(user)
	except TypeError:
		return bot.send_message(chat_id=chat_id,
								text=f'Nulla da confermare per {user}')

	# Controllo che il calciatore sia svincolato
	if utl.non_svincolato(pl):
		dbf.db_delete(
				table='offers',
				where=(f'offer_user = "{user}" AND ' +
				       'offer_status IS NULL'))
		return bot.send_message(
				chat_id=chat_id,
		        text=f'Giocatore non svincolato ({utl.non_svincolato(pl)}).')

	# Controllo che non si tratti di autorilancio
	if utl.autorilancio(user, pl):
		dbf.db_delete(
				table='offers',
				where=f'offer_user = "{user}" AND offer_status IS NULL')
		return bot.send_message(chat_id=chat_id,
		                        text="L'ultima offerta è già tua.")

	# Controllo che l'offerta superi l'ultimo rilancio ed eventuali autobids
	result = utl.check_offer_value(user, of_id, pl, dt)

	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		# Elimino eventuali offerte non confermate da altri user per lo stesso
		# calciatore
		dbf.db_delete(
				table='offers',
				where=f'offer_player = "{pl}" AND offer_status IS NULL AND ' +
				      f'offer_user != "{user}"')

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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')
	if cfg.BLOCK:
		group_id = cfg.POLPS_ID
	else:
		group_id = cfg.FANTA_ID

	user = select_user(update)

	# Controllo ci sia il pagamento e, se sì, lo seleziono.
	try:
		pay_id, pl, pr, mn = dbf.db_select(
				table='pays',
				columns=['pay_id', 'pay_player', 'pay_price', 'pay_money'],
				where=f'pay_user = "{user}" AND pay_status IS NULL')[0]
	except IndexError:
		return bot.send_message(chat_id=chat_id,
		                        text=f'Nulla da confermare per {user}')

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
				where=f'pay_user = "{user}" AND pay_player = "{pl}"')
		return bot.send_message(chat_id=chat_id,
		                        text=('Offerta insufficiente.\n' +
		                              f'Milioni mancanti: {pr - temp_bud}'))

	# Sommo al budget della fantasquadra il prezzo dei giocatori utilizzati
	# nel pagamento, se presenti, e che saranno quindi ceduti
	budget = dbf.db_select(
			table='budgets',
			columns=['budget_value'],
			where=f'budget_team = "{user}"')[0]

	new_budget = budget
	for i in mn:
		try:
			int(i)
		except ValueError:
			player = i.split(' (')[0]
			new_budget += dbf.db_select(
					table='players',
					columns=['player_price'],
					where=f'player_name = "{player}"')[0]

	# Qualora l'offerta sia valida, aggiorno varie voci nel db sia del
	# calciatore acquistato che di quelli ceduti, se presenti
	if new_budget < pr:
		dbf.db_delete(
				table='pays',
				where=f'pay_user = "{user}" AND pay_player = "{pl}"')
		return bot.send_message(chat_id=chat_id,
		                        text='Budget insufficiente')
	else:
		dbf.db_update(
					table='budgets',
					columns=['budget_value'],
					values=[new_budget - pr],
					where=f'budget_team = "{user}"')

		dbf.db_update(
					table='players',
					columns=['player_status'],
					values=[user],
					where=f'player_name = "{pl}"')

		# dbf.db_update(
		# 			table='stats',
		# 			columns=['status'],
		# 			values=[user],
		# 			where=f'name = "{pl}"')

		dbf.db_update(
					table='offers',
					columns=['offer_status'],
					values=['Official'],
					where=(f'offer_player = "{pl}" AND ' +
					      'offer_status = "Not Official"'))

		dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		dbf.db_update(
					table='pays',
					columns=['pay_dt', 'pay_status'],
					values=[dt, 'Confirmed'],
					where=f'pay_player = "{pl}"')

		for i in mn:
			try:
				int(i)
			except ValueError:
				player = i.split(' (')[0]
				dbf.db_update(
							table='players',
							columns=['player_status'],
							values=['FREE'],
							where=f'player_name = "{player}"')

				# dbf.db_update(
				# 			table='stats',
				# 			columns=['status'],
				# 			values=['FREE'],
				# 			where=f'name = "{player}"')

	message = (f'<i>{user}</i> ha ufficializzato ' +
	           f'<b>{pl}</b> a {pr}.\nPagamento: {", ".join(mn)}\n')

	if budget == new_budget - pr:
		message += f'Il budget resta {budget}'
	else:
		message += f'Il budget passa da {budget} a {new_budget - pr}.'

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	bot.send_message(chat_id=chat_id,
	                 text='Pagamento effettuato correttamente.')

	bot.send_message(parse_mode='HTML', chat_id=group_id,
	                 text=(message + cfg.SEPAR + utl.crea_riepilogo(dt)))

	# sf.aggiorna_rosa_online(user, (pl, pr), mn)


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
	if update.message.chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	# Elimino tutte le proposte di cancellazione non confermate dall'user
	dbf.db_delete(
			table='elimina',
			where=f'elimina_user = "{user}"')

	# Seleziono tutti gli autobids dell'user
	autobids = dbf.db_select(
			table='autobids',
			columns=['autobid_player'],
			where=f'autobid_user = "{user}"')
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
			table='autobids',
			columns=['autobid_id'],
			where=f'autobid_user = "{user}" AND autobid_player = "{jpl}"')[0]

	dbf.db_insert(
			table='elimina',
			columns=['elimina_ab', 'elimina_user'],
			values=[ab, user])

	message = (f"Stai eliminando l'autobid per <b>{jpl}</b>:" +
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
	if update.message.chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	g = open('info.txt', 'r')
	content = g.readlines()
	g.close()

	message = ''
	for row in content:
		row = row.replace('xx\n', ' ')
		message += row

	sf.logger.info(f'/INFO - {select_user(update)}')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def info_autobid(bot, update):

	"""
	Invia in chat le istruzioni sul funzionamento dell'autobid.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if update.message.chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	g = open('info_autobid.txt', 'r')
	content = g.readlines()
	g.close()

	message = ''
	for row in content:
		row = row.replace('xx\n', ' ')
		message += row

	sf.logger.info(f'/INFO_AUTOBID - {select_user(update)}')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	utl.aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutte le offerte precedenti non confermate dall'utente
	dbf.db_delete(
			table='offers',
			where=f'offer_user = "{user}" AND offer_status IS NULL')

	# Controllo che il formato sia giusto
	result = utl.check_offer_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		offer, pl = result

	# Aggiorno il db con i parametri che mancano
	pl_id = dbf.db_select(
			table='players',
			columns=['player_id'],
			where=f'player_name = "{pl}"')[0]

	team, roles, price = dbf.db_select(
			table='players',
			columns=['player_team', 'player_roles', 'player_price'],
			where=f'player_name = "{pl}"')[0]

	dbf.db_insert(
			table='offers',
			columns=['offer_user', 'offer_player', 'offer_player_id',
			         'offer_price'],
			values=[user, pl, pl_id, offer])

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
							text=f'Offri <b>{offer}</b> per:\n\n\t\t' +
							     f'<b>{pl}   ({team})   {roles}</b>' +
							     '\n\n/confermo_offerta')


def pago(bot, update, args):

	"""
	Aggiorna la tabella "pays" del db con lo status di "Not Confirmed".

	:param bot:
	:param update:
	:param args: list, input dell'user

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)
	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	utl.aggiorna_offerte_chiuse(datetime.strptime(dt, '%Y-%m-%d %H:%M:%S'))

	# Elimino dal db tutte i pagamenti precedenti non confermati dall'utente
	dbf.db_delete(
			table='pays',
			where=f'pay_user = "{user}" AND pay_status IS NULL')

	# Controllo che il formato sia corretto
	result = utl.check_pago_format(args)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		acquisto, pagamento = result

	# Creo il messaggio di conferma ed aggiorno il db con il pagamento
	# provvisorio
	result = utl.message_with_payment(user, acquisto, pagamento)
	if type(result) == str:
		return bot.send_message(chat_id=chat_id, text=result)
	else:
		money_db, message = result

	dbf.db_update(
			table='pays',
			columns=['pay_money'],
			values=[money_db],
			where=f'pay_user = "{user}" AND pay_status IS NULL')

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
	if chat_id == cfg.FANTA_ID:
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
							table='players',
			        columns=['player_team']), 3)
	if not tm:
		return bot.send_message(chat_id=chat_id,
		                        text='Squadra non riconosciuta, riprova.')

	pl = ef.jaccard_result(pl,
	                       dbf.db_select(
			                       table='players',
			                       columns=['player_name'],
	                               where=f'player_team = "{tm}"'), 3)
	if not pl:
		return bot.send_message(chat_id=chat_id,
		                        text='Calciatore non riconosciuto, riprova.')

	rl, pr, st = dbf.db_select(
			table='players',
            columns=['player_roles', 'player_price', 'player_status'],
			where=f'player_name = "{pl}"')[0]

	if st == 'FREE':
		st = 'Svincolato'

	message = (f'\t\t\t\t<b>{pl}</b> <i>({tm})   {rl}</i>\n\n' +
	           f'Squadra: <i>{st}</i>\nPrezzo: <b>{pr}</b>')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


def print_rosa(bot, update):

	"""
	Invia in chat un messaggio con la rosa dell'user, il numero di giocatori ed
	il budget disponibile.

	:param bot:
	:param update:

	:return: messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	message = f'<i>{user}</i> :\n'

	rosa = utl.order_by_role(user)

	for pl, tm, rl, pr in rosa:
		line = f'\n\t\t\t<b>{pl}</b> ({tm})   {rl}     {pr}'
		message += line

	budget = dbf.db_select(
			table='budgets',
			columns=['budget_value'],
			where=f'budget_team = "{user}"')
	budget = budget[0] if budget else 0

	message += (f'\n\nNumero di giocatori: <b>{len(rosa)}</b>\n' +
	            f'Milioni disponibili: <b>{budget}</b>')

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
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=utl.crea_riepilogo(dt))


def riepilogo_autobid(bot, update):

	"""
	Manda in chat gli autobid attivi dell'user che invia il comando.

	:param bot:
	:param update:

	:return: str, messaggio in chat

	"""

	chat_id = update.message.chat_id
	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	user = select_user(update)

	return bot.send_message(parse_mode='HTML', chat_id=chat_id,
	                        text=utl.crea_riepilogo_autobid(user))


def select_user(update):

	"""
	Mappa il nome di colui che invia il comando con la rispettiva fantasquadra.
	Utilizzata ovunque.

	:param update:

	:return user: str, nome fantasquadra

	"""

	return dbf.db_select(
			table='teams',
			columns=['team_name'],
			where=f'team_member = "{update.message.from_user.first_name}"')[0]


def ufficiali(bot, update):

	"""
	Crea il messaggio con le offerte già ufficializzate.

	:return message: messaggio in chat

	"""

	chat_id = update.message.chat_id
	uffic2print = 40

	if chat_id == cfg.FANTA_ID:
		return bot.send_message(chat_id=chat_id,
		                        text='Utilizza la chat privata')

	message = 'Ufficializzazioni:\n'

	uffic = dbf.db_select(
			table='offers',
			columns=['offer_id', 'offer_user', 'offer_player', 'offer_price'],
			where='offer_status = "Official"')

	if len(uffic) > uffic2print:
		uffic = uffic[-uffic2print:]

	for off_id, user, pl, pr in uffic:

		tm = dbf.db_select(
				table='players',
				columns=['player_team'],
				where=f'player_name = "{pl}"')[0]

		pagamento = dbf.db_select(
				table='pays',
				columns=['pay_money'],
				where=f'pay_offer = {off_id}')[0]

		message += (f'\n\t\t\t\t- <i>{user}</i> ' +
		            f'acquista <b>{pl}</b> ({tm}) a {pr}. ' +
		            f'Pagamento: <i>{pagamento}</i>.\n')

	return bot.send_message(parse_mode='HTML', chat_id=chat_id, text=message)


updater = Updater(token=cfg.TOKEN)
dispatcher = updater.dispatcher


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
