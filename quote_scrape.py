import logging

import urllib2

import codecs

from HTMLParser import HTMLParser

"""Util functions to scrape quotes from Goodreads"""

def _IsQuoteText(attrs):
  for pair in attrs:
    key, val = pair
    if key == 'class':
      if val == 'quoteText':
        return True
  return False

class QuoteParser(HTMLParser):

  def __init__(self):
    HTMLParser.__init__(self)

    self.quotes = []
    self.in_quote = False

  def handle_starttag(self, tag, attrs):
    if _IsQuoteText(attrs):
      self.in_quote = True

  def handle_data(self, data):
    if self.in_quote:
      data = data.strip()
      if data:
        quote = codecs.decode(data, 'utf-8')
        self.quotes.append(data)
        self.in_quote = False

def _ReadUrl(url):
  return urllib2.urlopen(url).read()

def _ExtractQuotes(content):
  parser = QuoteParser()
  parser.feed(content)
  return parser.quotes

def ScrapeQuotes(author_id):

  base_url = "http://www.goodreads.com/author/quotes/%d" % author_id

  quotes = []

  page_url = base_url + '?page=%d'

  page = 1

  while True:
    fetch_url = page_url % page
    logging.info('fetching quotes from %s' , fetch_url)

    content = _ReadUrl(fetch_url)
    page_quotes = _ExtractQuotes(content)

    logging.info('found quotes: %d', len(page_quotes))

    if page_quotes:
      quotes.extend(page_quotes)
    else:
      logging.info('all done')
      return quotes

    page += 1


def main():
  """Command-line demo that dumps quotes."""

  logging.basicConfig(level=logging.DEBUG)
  # chomsky, for an example
  print ScrapeQuotes(2476)


if __name__ == '__main__':
  main()
