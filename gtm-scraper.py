import requests, sys, csv, bs4, re
from urllib.parse import urlparse

# Get the hostnames to check from the command line arguments
valid_hostnames = sys.argv[1:]

queued_urls = [] # working list of urls to check
checked_urls = [] # everything that was reviewed
errored_urls = [] # everything that failed its request status
page_details = {} # dictonary of pages as keys and lists of containers as values

def get_page(url):
    # Get the URL and return it as a Beautiful Soup object
    res = requests.get(url)

    try:
        res.raise_for_status()
    except requests.exceptions.RequestException:
        errored_urls.append(url)
        return None

    pageSoup = bs4.BeautifulSoup(res.text, 'html.parser')
    return pageSoup

def find_urls_on_page(current_url, bs4_obj):
    # Take a Beautiful Soup object, find everything that looks like a link
    # then return all valid, unchecked, unqueued links
    global valid_hostnames
    global queued_urls
    global checked_urls
    global errored_urls

    anchors = bs4_obj.select('a[href]')

    # Get rid of any links to call or email and any links that just run a script
    real_links = []
    invalid_link_regex = re.compile(r'^(mailto|tel|javascript):|\.(png|jpe?g|gif|pdf|xlsx?|docx?|pptx?|zip|txt|mpeg)$', re.IGNORECASE)

    for anchor in anchors:
        href = anchor.get('href')
        if invalid_link_regex.search(href) is None:
            real_links.append(href)
    
    # Narrow the list down to just scheme, hostname, and path - no parameters or fragments
    base_links = []
    current_hostname = urlparse(current_url).hostname

    for link in real_links:
        base_url = 'https://'
        parsed_link = urlparse(link)
        if parsed_link.hostname:
            base_url = base_url + parsed_link.hostname + parsed_link.path
        else:
            base_url = base_url + current_hostname + parsed_link.path

        base_links.append(base_url)

    # Only return the valid links that haven't been already queued, checked, or resulted in an error
    return_links = []

    for link in base_links:
        if urlparse(link).hostname in valid_hostnames:
            if link not in queued_urls and link not in checked_urls and link not in errored_urls:
                return_links.append(link)
    
    return return_links

def find_gtm_containers(bs4_obj):
    # Take a Beautiful Soup object, find all scripts in the head and no scripts in the body,
    # then return a list of dictionaries with container id, as well as placement details
    containers = []

    head_scripts = bs4_obj.select('head script')
    gtm_scripts = []

    for script in head_scripts:
        if re.search('googletagmanager', str(script)):
            gtm_scripts.append(script)

    gtm_noscripts = bs4_obj.select('body noscript iframe[src*="googletagmanager"]')

    container_id_regex = re.compile(r'GTM-[A-Z0-9]+')

    head_container_ids = []
    noscript_container_ids = []
    unique_container_ids = []

    for script in gtm_scripts:
        match = container_id_regex.search(str(script))
        if match:
            match_result = match.group(0)
            if match_result not in head_container_ids:
                head_container_ids.append(match_result)
            if match_result not in unique_container_ids:
                unique_container_ids.append(match_result)
    
    for noscript in gtm_noscripts:
        match = container_id_regex.search(str(noscript))
        if match:
            match_result = match.group(0)
            if match_result not in noscript_container_ids:
                noscript_container_ids.append(match_result)
            if match_result not in unique_container_ids:
                unique_container_ids.append(match_result)

    for container_id in unique_container_ids:
        container = {
            "id": container_id,
            "in_head": container_id in head_container_ids,
            "in_body": container_id in noscript_container_ids
        }
        containers.append(container)
    
    return containers

def write_result_to_file(dictionary):
    global valid_hostnames

    # For lack of a better option at the moment, start the name with the first hostname in the list from the command line
    name_root = valid_hostnames[0].replace('.','_')
    with open(f'{name_root}-gtm-scraper-results.csv', 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['url', 'container_id', 'in_head', 'in_body'])

        for key, value in dictionary.items():
            if len(value) >= 1:
                for container in value:
                    container_id = container["id"]
                    head_bool = container["in_head"]
                    body_bool = container["in_body"]
                    writer.writerow([key, container_id, head_bool, body_bool])
            else:
                writer.writerow([key, 'none', 'na', 'na'])

# Initialize the queue with the homepages for the hostnames from the command line
for hostname in valid_hostnames:
    queued_urls.append(f'https://{hostname}/')

# Check pages until the queue is empty
while queued_urls:
    current_url = queued_urls.pop(0)
    current_page = get_page(current_url)
    if current_page:
        checked_urls.append(current_url) # make sure it's in one of the lists so that it doesn't get enqueued
        queued_urls.extend(find_urls_on_page(current_url, current_page))
        page_details[current_url] = find_gtm_containers(current_page)

# Use the dictionary to create a csv file
write_result_to_file(page_details)