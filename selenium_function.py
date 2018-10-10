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

	url_acquisti = ('https://leghe.fantagazzetta.com/fantascandalo/' +
	                'gestione-lega/acquista-calciatore')

	brow.get(url_acquisti)

	if fantasquadra != 'Ciolle United':
		select_team(brow, fantasquadra)

	pl_path = './/input[@name="keywords"]'
	wait_visible(brow, WAIT, pl_path)
	pl_box = brow.find_element_by_xpath(pl_path)
	pl_box.send_keys(acquisti[0])

	brow.find_element_by_xpath(
		'.//td[@data-key="actions"]//span[@class="check"]').click()
	brow.find_element_by_xpath('.//a[@class="finalizing-hidden cart"]').click()

	pr_path = './/input[@class="number"]'
	wait_visible(brow, WAIT, pr_path)
	pr_box = brow.find_element_by_xpath(pr_path)
	pr_box.clear()
	pr_box.send_keys(acquisti[1])
	time.sleep(1)

	# brow.find_element_by_xpath('.//button[@onclick="buyPlayers()"]').click()
	time.sleep(3)

	logger.info('AGGIORNA_ACQUISTI - Acquisto di {} '.format(acquisti[0]) +
	            'da parte di {} effettuato correttamente'.format(fantasquadra))

	brow.close()


def aggiorna_cessioni(brow, fantasquadra, cessioni):

	url_cessioni = ('https://leghe.fantagazzetta.com/fantascandalo/' +
	                'gestione-lega/svincola-calciatore')

	brow.get(url_cessioni)

	if fantasquadra != 'Ciolle United':
		select_team(brow, fantasquadra)

	table = './/div[@id="playersBox"]'
	wait_visible(brow, WAIT, table)

	pls = brow.find_elements_by_xpath(table + '//tr[@data-lock="1"]')

	for pl in pls:
		scroll_to_element(brow, 'false', pl)
		name = pl.find_element_by_xpath('.//td[@data-key="name"]').text
		if name.upper() in cessioni:
			pl.find_element_by_xpath('.//span[@class="check"]').click()

	brow.find_element_by_xpath('.//a[@class="finalizing-hidden cart"]').click()

	release = './/button[@onclick="releasePlayers()"]'
	wait_clickable(brow, WAIT, release)
	time.sleep(2)
	brow.find_element_by_xpath(release).click()
	time.sleep(3)

	logger.info('AGGIORNA_CESSIONI - ' +
	            'Cessioni di {} '.format(', '.join(cessioni)) +
	            'da parte di {} effettuato correttamente'.format(fantasquadra))


def close_popup(brow):

	accetto = './/button[@class="qc-cmp-button"]'

	try:
		wait_clickable(brow, WAIT, accetto)
		brow.find_element_by_xpath(accetto).click()
	except TimeoutException:
		pass


def login():

	url_lega = 'https://leghe.fantagazzetta.com/fantascandalo/home'

	brow = webdriver.Chrome(chrome_path)
	time.sleep(3)

	brow.get(url_lega)

	close_popup(brow)
	brow.refresh()

	accedi = ('.//button[@class="hidden-logged btn btn-primary btn-sm ' +
	          'btn-raised navbar-btn navbar-right mw-auto"]')
	for i in range(trials):
		try:
			wait_clickable(brow, WAIT, accedi)
			break
		except TimeoutException:
			if i < trials:
				brow.close()
				login()
			else:
				logger.info('LOGIN - "Accedi" button not found')
				brow.close()

	brow.find_element_by_xpath(accedi).click()

	f = open('login.txt', 'r')
	credentials = f.readlines()
	f.close()

	username, password = credentials[0].split(', ')

	user_path = './/input[@name="username"]'
	pass_path = './/input[@name="password"]'
	accedi_path = './/button[@id="buttonLogin"]'
	wait_visible(brow, WAIT, user_path)
	wait_visible(brow, WAIT, pass_path)
	user = brow.find_element_by_xpath(user_path)
	passw = brow.find_element_by_xpath(pass_path)

	user.send_keys(username)
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

	teams = brow.find_elements_by_xpath('.//ul[@class="competition-list"]//a')
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
