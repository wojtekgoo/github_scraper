import getpass  # to hide password
import requests  # for HTTP requests
from bs4 import BeautifulSoup  # for web scraping
import xlrd  # to read from Excel
import warnings  # suppress warnings
import Queue  # to create queue of links to scrap
import threading
from datetime import datetime

startTime = datetime.now()

base_url = "https://github.com"
s = requests.session()  # preserve session
global_lock = threading.Lock()


#### FUNCTIONS ####

# extract authenticity_token
def extract_token(res):
    soup = BeautifulSoup(res.text)
    input_tag = soup.select('input[value]')  # get all <input> elems
    token = input_tag[1]['value']  # first match will have value='auth token' attribute. Get that value.
    return token


# extract links to search results
def scrap_page(soup, output):
    results = soup.findAll("div", {"class": "d-inline-block col-10"})  # search results have this class name
    for item in results:
        a_tags = item.findAll('a')  # extract <a> tags from each result
        for a in a_tags:
            if a.get('title') is not None:  # keep only those links that have 'title' attribute
                output.append(a['href'])


def create_queue(links, cookies, filename):
    q = Queue.Queue()
    [q.put(a) for a in links]
    threads = []
    for i in range(10):
        t = threading.Thread(target=get_raw, args=(q, cookies, filename))
        t.daemon = True
        t.start()
        threads.append(t)

    q.join()
    [t.join() for t in threads]


# get raw data from search result
def get_raw(q, cookies, filename):
    while not q.empty():

        #		while global_lock.locked():	# continue to check if thread can take its turn
        #			continue
        #		global_lock.acquire()

        try:
            link = q.get_nowait()  # remove item from queue
        except:  # if queue empty, Python throws exception
            #			global_lock.release()	# release lock and quit thread
            return

        res = s.get(link, cookies=cookies, verify=False)
        soup = BeautifulSoup(res.text)
        link_container = soup.find(lambda tag: tag.name == 'div' and tag.get('class') == [
            'BtnGroup'])  # find <div> tag with link to Raw inside
        a = link_container.find('a')['href']  # extract first href from that container - this is link to the Raw file
        a = base_url + a
        raw_page = s.get(a, cookies=cookies, verify=False)  # GET raw page

        with open(filename, mode='a+') as myfile:
            myfile.write('\n\n' + '=' * 60 + ' URL ' + '=' * 60 + '\n' + a + '\n\n')
            myfile.write(raw_page.text)
            myfile.close()

        #		global_lock.release()
        q.task_done()  # send signal to queue that task has been completed


def main():
    # suppress all warnings
    warnings.filterwarnings("ignore")

    res = s.get(base_url + "/login", verify=False)  # GET github page to get cookies

    csrf = extract_token(res)

    # Create payload for POST request
    login = raw_input("login: ")
    password = getpass.getpass()
    payload = {'login': login, 'password': password, 'authenticity_token': csrf}
    cookies = dict(res.cookies)
    cookies['authenticity_token'] = csrf

    # Initial POST login
    res = requests.post(base_url + "/session", data=payload, verify=False, cookies=cookies)

    # Get cookies from server response and add CSRF token for future requests
    cookies = dict(res.cookies)
    cookies['authenticity_token'] = csrf

    # Open Excel with queries
    xl_workbook = xlrd.open_workbook("findings.xlsx")
    xl_sheet = xl_workbook.sheet_by_name("Sheet1")
    row = 1
    while (row < xl_sheet.nrows):
        print "Processing query: " + str(row) + "\n"
        url = xl_sheet.cell_value(row, 3)
        keyword = xl_sheet.cell_value(row, 0)
        file = xl_sheet.cell_value(row, 1)
        row = row + 1

        res = s.get(url, cookies=cookies, verify=False)
        soup = BeautifulSoup(res.text)

        # if no results, class 'blankslate' will be created in page source
        if (soup.find("div", {"class": "blankslate"})):
            continue

        output = []  # list to contain results

        # check if there are more than 1 page with search results
        pagination = soup.find("div", {"class": "d-flex d-md-inline-block pagination"})  # find <div> with <class = "pagination"> attribute
        if (pagination):
            # scrap 1st page
            results = soup.findAll("div", {"class": "flex-auto min-width-0 col-10"})  # search results have this class name
            for item in results:
                a_tags = item.findAll('a')  # extract <a> tags from each result
                for a in a_tags:
                    if a.get('title') is not None:  # keep only those links that have 'title' attribute
                        output.append(a['href'])

            # scrap rest of pages
            hrefs = pagination.findAll('a')  # Return all href elements within this <div> tag
            last_page_index = hrefs[-2].text  # This is index of last page in search results
            for j in range(1, int(last_page_index)):
                url = base_url + hrefs[-1][
                    'href']  # Create URL for next page from search results, based on base_URL and value from "Next" link
                res = s.get(url, cookies=cookies, verify=False)  # Navigate to next page from search results
                # Find again link to "Next" page and append to base_URL
                soup = BeautifulSoup(res.text)
                pagination = soup.find("div", {"class": "pagination"})
                hrefs = pagination.findAll('a')
                scrap_page(soup, output)

        # if there is only one page with search results
        else:
            scrap_page(soup, output)

        output_full = [base_url + x for x in output]

        #### At this point we have a list with links to the search results 	####
        #### We want to visit each result and get link to the Raw version 	####
        #### We do it with threads. Each thread visits one search result, gets raw data and appends to file	####

        filename = keyword + " in " + file + ".txt"
        create_queue(output_full, cookies, filename)

    print datetime.now() - startTime


if __name__ == '__main__':
    main()