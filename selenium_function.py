import os
import time
import log_functions as log
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver

chrome_path = os.getcwd() + '/chromedriver'
WAIT = 60
logger = log.set_logging()
trials = 3


def aggiorna_acquisti(brow, fantasquadra, acquisti):

	"""
	Aggiorna gli acquisti ufficiali subito dopo il pagamento tramite bot.
	Utilizzata all'interno di confermo_pagamento().

	:param brow: browser
	:param fantasquadra: str
	:param acquisti: tuple, (calciatore, prezzo)

	:return: nulla

	"""

	url_acquisti = ('https://leghe.fantagazzetta.com/fantascandalo/' +
	                'gestione-lega/acquista-calciatore')

	brow.get(url_acquisti)

	# Seleziona la squadra da aggiornare sul sito
	select_team(brow, fantasquadra)

	# Inserisce il nome del calciatore nel box degli svincolati
	pl_box_path = './/input[@name="keywords"]'
	for i in range(trials):
		try:
			wait_visible(brow, WAIT, pl_box_path)
			pl_box = brow.find_element_by_xpath(pl_box_path)
			pl_box.send_keys(acquisti[0])
			break
		except TimeoutException:
			if i < trials:
				logger.info('AGGIORNA_ACQUISTI - Box per inserire il nome ' +
				            'del calciatore non trovato.' +
				            'Tentativo: {}'.format(i + 1))
				brow.refresh()
				return aggiorna_acquisti(brow, fantasquadra, acquisti)
			else:
				logger.info('AGGIORNA_ACQUISTI - Box per inserire il nome ' +
				            'del calciatore non trovato. Chiudo il browser.')
				brow.close()

	# Inserisce il segno di spunta per confermare il calciatore selezionato
	brow.find_element_by_xpath(
		'.//td[@data-key="actions"]//span[@class="check"]').click()

	# Clicca il tasto 'PROCEDI'
	brow.find_element_by_xpath('.//a[@class="finalizing-hidden cart"]').click()

	# Inserisce il prezzo di acquisto nel box corrispondente
	pr_path = './/input[@class="number"]'
	for i in range(trials):
		try:
			wait_visible(brow, WAIT, pr_path)
			pr_box = brow.find_element_by_xpath(pr_path)
			pr_box.clear()
			pr_box.send_keys(acquisti[1])
			break
		except TimeoutException:
			if i < trials:
				logger.info('AGGIORNA_ACQUISTI - Box per inserire il prezzo ' +
				            'del calciatore non trovato.' +
				            'Tentativo: {}'.format(i + 1))
				brow.refresh()
				return aggiorna_acquisti(brow, fantasquadra, acquisti)
			else:
				logger.info('AGGIORNA_ACQUISTI - Box per inserire il prezzo ' +
				            'del calciatore non trovato. Chiudo il browser.')
				brow.close()

	# Clicca il tasto 'COMPLETA ACQUISTO'
	compl_acq = './/button[@onclick="releasePlayers()"]'
	for i in range(trials):
		try:
			wait_clickable(brow, WAIT, compl_acq)
			time.sleep(2)
			brow.find_element_by_xpath(
				'.//button[@onclick="buyPlayers()"]').click()
			time.sleep(2)
			break
		except TimeoutException:
			if i < trials:
				logger.info('AGGIORNA_ACQUISTI - Tasto "COMPLETA ACQUISTO" ' +
				            'non trovato. Tentativo {}'.format(i + 1))
				brow.refresh()
				return aggiorna_acquisti(brow, fantasquadra, acquisti)
			else:
				logger.info('AGGIORNA_ACQUISTI - Tasto "COMPLETA ACQUISTO" ' +
				            'non trovato. Chiudo il browser.')
				brow.close()

	logger.info('AGGIORNA_ACQUISTI - Acquisto di {} '.format(acquisti[0]) +
	            'da parte di {} effettuato correttamente'.format(fantasquadra))

	brow.close()


def aggiorna_cessioni(brow, fantasquadra, cessioni):

	"""
	Aggiorna le cessioni ufficiali subito dopo il pagamento tramite bot.
	Utilizzata all'interno di confermo_pagamento().

	:param brow: browser
	:param fantasquadra: str
	:param cessioni: list, [calciatore1, calciatore2, ....]

	:return: nulla

	"""

	url_cessioni = ('https://leghe.fantagazzetta.com/fantascandalo/' +
	                'gestione-lega/svincola-calciatore')

	brow.get(url_cessioni)

	select_team(brow, fantasquadra)

	# Tabella contenente la rosa della fantasquadra in questione
	table = './/div[@id="playersBox"]'
	for i in range(trials):
		try:
			wait_visible(brow, WAIT, table)
			break
		except TimeoutException:
			if i < trials:
				logger.info('AGGIORNA_CESSIONI - Rosa non trovata.' +
				            'Tentativo: {}'.format(i + 1))
				brow.refresh()
				return aggiorna_cessioni(brow, fantasquadra, cessioni)
			else:
				logger.info('AGGIORNA_CESSIONI - Rosa non trovata.' +
				            'Chiudo il browser.')
				brow.close()

	# Tutti i calciatori della rosa
	pls = brow.find_elements_by_xpath(table + '//tr[@data-lock="1"]')

	# Scorro tutta la rosa e spunto solo i calciatori da cedere
	for pl in pls:
		scroll_to_element(brow, 'false', pl)
		name = pl.find_element_by_xpath('.//td[@data-key="name"]').text
		if name.upper() in cessioni:
			pl.find_element_by_xpath('.//span[@class="check"]').click()

	# Clicca il tasto 'PROCEDI'
	brow.find_element_by_xpath('.//a[@class="finalizing-hidden cart"]').click()

	# Clicca il tasto 'COMPLETA SVINCOLO'
	release = './/button[@onclick="releasePlayers()"]'
	for i in range(trials):
		try:
			wait_clickable(brow, WAIT, release)
			time.sleep(2)
			brow.find_element_by_xpath(release).click()
			time.sleep(2)
			break
		except TimeoutException:
			if i < trials:
				logger.info('AGGIORNA_CESSIONI - Tasto "COMPLETA SVINCOLO" ' +
				            'non trovato. Tentativo {}'.format(i + 1))
				brow.refresh()
				return aggiorna_cessioni(brow, fantasquadra, cessioni)
			else:
				logger.info('AGGIORNA_CESSIONI - Tasto "COMPLETA SVINCOLO" ' +
				            'non trovato. Chiudo il browser.')
				brow.close()

	logger.info('AGGIORNA_CESSIONI - ' +
	            'Cessioni di {} '.format(', '.join(cessioni)) +
	            'da parte di {} effettuate correttamente'.format(fantasquadra))


def chiudi_popup(brow):

	"""
	Clicca sul tasto 'ACCETTO' per chiudere il popup che si apre al momento
	della connessione.
	Utilizzata all'interno di login().

	:param brow:

	:return: nulla

	"""

	accetto = './/button[@class="qc-cmp-button"]'

	try:
		wait_clickable(brow, WAIT, accetto)
		brow.find_element_by_xpath(accetto).click()
	except TimeoutException:
		logger.info('CHIUDI_POPUP - Popup non trovato.')
		pass


def login():

	"""
	Si collega al sito della lega ed effettua il login con le credenziali delle
	Ciolle.
	Utilizzata all'interno di confermo_pagamento().

	:return:

	"""

	url_lega = 'https://leghe.fantagazzetta.com/fantascandalo/home'

	brow = webdriver.Chrome(chrome_path)
	time.sleep(3)

	brow.get(url_lega)

	chiudi_popup(brow)

	# Clicca il tasto 'ACCEDI'
	accedi = ('.//button[@class="hidden-logged btn btn-primary btn-sm ' +
	          'btn-raised navbar-btn navbar-right mw-auto"]')
	for i in range(trials):
		try:
			wait_clickable(brow, WAIT, accedi)
			brow.find_element_by_xpath(accedi).click()
			break
		except TimeoutException:
			if i < trials:
				logger.info('LOGIN - Tasto "ACCEDI" non trovato.' +
				            'Tentativo {}'.format(i + 1))
				brow.close()
				return login()
			else:
				logger.info('LOGIN - Tasto "ACCEDI" non trovato.' +
				            'Chiudo il browser.')
				brow.close()

	# Carica username e password
	f = open('login.txt', 'r')
	credentials = f.readlines()
	f.close()
	username, password = credentials[0].split(', ')

	# Inserisco l'username
	user_path = './/input[@name="username"]'
	for i in range(trials):
		try:
			wait_visible(brow, WAIT, user_path)
			user = brow.find_element_by_xpath(user_path)
			user.send_keys(username)
			break
		except TimeoutException:
			if i < trials:
				logger.info('LOGIN - Box per username non trovato.' +
				            'Tentativo {}'.format(i + 1))
				brow.close()
				return login()
			else:
				logger.info('LOGIN - Box per username non trovato.' +
				            'Chiudo il browser.')
				brow.close()

	pass_path = './/input[@name="password"]'
	accedi_path = './/button[@id="buttonLogin"]'
	wait_visible(brow, WAIT, pass_path)
	passw = brow.find_element_by_xpath(pass_path)

	passw.send_keys(password)
	wait_clickable(brow, WAIT, accedi_path)
	accedi = brow.find_element_by_xpath(accedi_path)
	accedi.click()

	lega = './/span[@class="league-name"]'

	for i in range(trials):
		try:
			wait_clickable(brow, WAIT, lega)
			break
		except TimeoutException:
			if i < trials:
				brow.refresh()
				login()
			else:
				logger.info('LOGIN - "Fantascandalo" button not found')
				brow.close()

	return brow


def scroll_to_element(brow, true_false, element):

	"""
	If the argument of 'scrollIntoView' is 'true' the command scrolls
	the webpage positioning the element at the top of the window, if it
	is 'false' the element will be positioned at the bottom.
	"""

	brow.execute_script('return arguments[0].scrollIntoView({});'
						   .format(true_false), element)


def select_team(brow, fantasquadra):

	# Facendo il login con le nostre credenziali la nostra squadra è
	# selezionata di default. Passando 'Ciolle United' al codice sottostante si
	# produrrebbe un errore in quanto l'elemento associato non è cliccabile.
	if fantasquadra != 'Ciolle United':

		arrow = './/a[@href="#teamsDropdown"]'

		for i in range(trials):
			try:
				wait_clickable(brow, WAIT, arrow)
				break
			except TimeoutException:
				if i < trials:
					brow.refresh()
					select_team(brow, fantasquadra)
				else:
					logger.info('SELECT_TEAM - Arrow button not found')
					brow.close()

		brow.find_element_by_xpath(arrow).click()

		teams = brow.find_elements_by_xpath(
				'.//ul[@class="competition-list"]//a')
		for team in teams:
			if team.text == fantasquadra:
				scroll_to_element(brow, 'false', team)
				team.click()
				break


def wait_clickable(brow, seconds, element):

	"""
	Forces the script to wait for the element to be clickable before doing
	any other action.
	"""

	WebDriverWait(
			brow, seconds).until(EC.element_to_be_clickable(
					(By.XPATH, element)))


def wait_visible(brow, seconds, element):

	"""
	Forces the script to wait for the element to be visible before doing
	any other action.
	"""

	WebDriverWait(
			brow, seconds).until(EC.visibility_of_element_located(
					(By.XPATH, element)))


login()
