import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from collections import Counter
import re


# Decyzja o tym aby najpierw zastosować Selenium do scrapowania artykułów, a następnie zwykłe scrapowanie
# została podjeta na podstawie analizy wyników scrapowania artykułów z różnych stron. W przypadku niektórych stron
# kategorie artykułów i data publikacji  były dostępne tylko w tagach script, z którymi
# zwykłe requesty miały problem. O ile zwykłe requesty były w stanie pobrać treść tych tagów, to nie zawsze były
# to kompletne dane, np. były wstanie zwrócić tylko tylko tylko ostatni element z listy kategorii, a nie wszystkie,
# czy nie były wstanie zwrócić daty publikacji. Dlatego zdecydowałem się na zastosowanie Selenium jako pierwszej metody.

def scrape_article_with_selenium(url):
    # Wyslanie zapytania do strony z uzyciem Selenium
    service = Service(ChromeDriverManager().install())
    options = Options()
    options.headless = True

    driver = webdriver.Chrome(service=service, options=options)
    try:
        driver.get(url)
        content = driver.page_source
    finally:
        driver.quit()

    soup = BeautifulSoup(content, 'html.parser')

    # Wyciagniecie tytulu, kategorii, daty publikacji i tresci
    title = soup.find('title').get_text().strip()
    category = extract_category(soup)
    date_published = extract_date_published(soup)
    content = extract_content(soup)

    # Zwrocenie danych artykulu
    article_data = {
        'link': url,
        'title': title,
        'category': category,
        'date_published': date_published,
        'content': content
    }
    return article_data

def scrape_article(url):
    try:
        # Wyslanie zapytania do strony
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Parsowanie HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Wyciagniecie tytulu, kategorii, daty publikacji i tresci
        title = soup.find('title').get_text().strip()
        category = extract_category(soup)
        date_published = extract_date_published(soup)
        content = extract_content(soup)

        # Zwrocenie danych artykulu
        article_data = {
            'link': url,
            'title': title,
            'category': category,
            'date_published': date_published,
            'content': content
        }
        return article_data

    except requests.exceptions.RequestException as e:
        print(f"Error scraping {url}: {e}")
        return None

def extract_category(soup):
    # Wyciagniecie kategorii z tagow HTML lub z script tagow
    category = None
    script_tag = soup.find_all('script', type='application/ld+json')
    for script in script_tag:
        try:
            json_data = json.loads(script.string)
            if 'keywords' in json_data:
                category = ', '.join(json_data['keywords'])
                return category
            if 'articleSection' in json_data :
                category = ', '.join(json_data['articleSection'])  #
                return category
        except json.JSONDecodeError:
            continue

    if not category:
        category = soup.find('meta', {'name': 'category'})
        if not category:
            category = soup.find('meta', {'name': 'keywords'})
        if not category:
            category = soup.find('meta', {'name': 'news_keywords'})
        if not category:
            category = soup.find('meta', {'property': 'article:section'})
        return category['content'] if category else 'No category found'

def parse_iso_date(iso_date):
    #Formatowanie daty
    try:
        dt = datetime.fromisoformat(iso_date.rstrip('Z'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return iso_date

def extract_date_published(soup):
    # Wyciagniecie daty publikacji z tagow HTML lub z script tagow
    pub_date = None
    script_tags = soup.find_all('script', type='application/ld+json')
    for script in script_tags:
        try:
            json_data = json.loads(script.string)
            if 'datePublished' in json_data:
                pub_date = parse_iso_date(json_data['datePublished'])
        except json.JSONDecodeError:
            continue

    if not pub_date:
        pub_date_tag = soup.find('meta', {'property': 'article:published_time'})
        if pub_date_tag:
            pub_date = pub_date_tag.get('content')
    if not pub_date:
        pub_date_tag = soup.find('meta', {'name': 'pubdate'})
        if pub_date_tag:
            pub_date = pub_date_tag.get('content')
    if not pub_date:
        pub_date_tag = soup.find('time')
        if pub_date_tag:
            pub_date = pub_date_tag.get_text().replace('\n', '')
    if pub_date:
        return pub_date
    return ""

def extract_content(soup):
    content_tags = soup.find_all(['h2', 'h3', 'p'])
    #content += "".join([str(tag) for tag in content_tags]) #Zwraca text z tagami HTML
    content = "".join([tag.get_text(separator='\n') for tag in content_tags]) #Zwraca tylko tekst
    return content

def integrate_serp_results(keyword):
    banned_domains = load_banned_domains()
    serp_results = fetch_serp_results(keyword)

    #Wczytanie wyników SERP z pliku
    #serp_results = json.load(open('search_results.json', 'r', encoding='utf-8'))

    if not serp_results:
        print(f"Failed to fetch SERP results for '{keyword}'.")
        return []

    urls_to_scrape = [result['link'] for result in serp_results['organicResults'] if get_domain_from_url(result['link']) not in banned_domains]
    scraped_articles = []
    current_index = 0

    while len(scraped_articles) <= 3 and current_index < len(urls_to_scrape):
        url = urls_to_scrape[current_index]
        current_index += 1
        domain = get_domain_from_url(url)

        if domain in banned_domains:
            continue

        article_data_with_selenium = scrape_article_with_selenium(url)


        if article_data_with_selenium:
            if len(article_data_with_selenium['content']) >= 1500:
                scraped_articles.append(article_data_with_selenium)
            else:
                save_banned_domain(domain)
        else:
            # Jeśli scraping Selenium nie powiódł się, próba zwykłego scrapowania
            article_data = scrape_article(url)
            if article_data:
                if len(article_data['content']) >= 1500:
                     scraped_articles.append(article_data)
                else:
                    save_banned_domain(domain)



    return scraped_articles

def load_banned_domains(file_path='banned_domains.txt'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_banned_domain(domain, file_path='banned_domains.txt'):
    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(domain + '\n')


def get_domain_from_url(url):
    # Wyciagniecie domeny z URL
    return url.split('/')[2]


def fetch_serp_results(keyword, num_results=10):
    api_key = 'Api Key' # Wstawienie klucza API
    url = 'http://api.hasdata.com/google-serp/serp'

    params = {
        'q': keyword,
        'location': 'Poland',
        'deviceType': 'desktop',
        'gl': 'pl',
        'hl': 'pl',
        'num': num_results,  # ilosc artykułów do pobrania
    }

    headers = {
        'Authorization': f'Bearer {api_key}',
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()

        serp_results = response.json()
        return serp_results

    except requests.exceptions.RequestException as e:
        print(f"Error fetching SERP results for '{keyword}': {e}")
        return None



def calculate_statistics(articles):
    num_articles = len(articles)
    total_words = 0
    word_count = Counter()

    for article in articles:
        # Wyciagniecie tekstu z tagow HTML
        text = re.sub(r'<.*?>', ' ', article['content'])
        words = text.split()
        total_words += len(words)
        word_count.update(words)

    average_words = total_words / num_articles if num_articles > 0 else 0
    most_common_words = word_count.most_common(5)

    statistics = {
        'num_articles': num_articles,
        'total_words': total_words,
        'average_words': average_words,
        'most_common_words': most_common_words
    }

    return statistics

def generate_output(keyword):
    # Pobranie zapytania SERP i  scraping artykułów
    scraped_articles = integrate_serp_results(keyword)

    if not scraped_articles:
        print("No articles were scraped.")
        return

    # Kalkulacja statystyk
    statistics = calculate_statistics(scraped_articles)

    # Generacja wynikowego JSON
    result = {
        'articles': scraped_articles,
        'statistics': statistics
    }

    # Zapisanie wyniku do pliku
    with open('response_with_statistics.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Output generated and saved to response_with_statistics.json")

def main_scraping(keyword):
    generate_output(keyword)

if __name__ == "__main__":
    #Step 1
    urls_to_scrape = [
        'https://www.gram.pl/artykul/top-10-najbardziej-wyczekiwane-gry-planszowe-2024-roku',
        'https://planszeo.pl/kalendarz-premier-i-dodrukow'
    ]
    articles = [scrape_article_with_selenium(url) for url in urls_to_scrape]
    print(calculate_statistics(articles))
    with open('response.json', 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    #Step 2 and 3
    #main_scraping('najlepsze gry planszowe 2024')