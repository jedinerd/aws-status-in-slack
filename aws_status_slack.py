#!/usr/bin/python
""" Poll data from AWS status RSS feed and notify changes in Slack.
"""
import argparse
import datetime
import logging
import time
import sys
import requests
import json
import feedparser

# Setup logging
logging.getLogger('requests').setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, datefmt='%H:%M:%S',
                    format='[%(levelname)s][%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

# Setup constants
START_TIME = datetime.datetime.now()
AWS_RSS_URL = 'http://status.aws.amazon.com/rss/%s.rss'
REQUESTS_INTERVAL = 2 # Time in seconds between feeds requests
CHECKS_INTERVAL = 60 # Time in seconds between all feeds checking

def fetch(feed):
    """ Fetch feed.
    Args:
        feed (str): name of the feed to be fetched.
    Return:
        feedparser.FeedParserDict: parsed feed.
    """
    return feedparser.parse(AWS_RSS_URL % feed)

def last_pub_date(data):
    """ Get publication date of latest item in feed.
    Args:
        data (feedparser.FeedParserDict): parsed feed.
    Return:
        datetime: publication date of latest item in feed or START_TIME if no
            publication is found.
    """
    # Return published date as a datetime object.
    # Note that d.entries[0].published_parsed is a time.struct_time
    return datetime.datetime(*data.entries[0].published_parsed[:6])

def send_to_slack(item, slack_webhook, slack_channel):
    # Get message color:
    if 'Service is operating normally:' in item.title:
        color = 'good'
    elif 'Informational message:' in item.title:
        color = 'warning'
    else:
        color = 'danger'

    payload = {
      'username': 'aws',
      'icon_url': 'https://dl.dropboxusercontent.com/u/62469907/aws-icon.png',
      'channel': slack_channel,
      'attachments': [
        {
          'color': color,
          'title':  item.title,
          'title_link': item.link,
          'text': item.summary
        }
      ]
    }

    requests.post(slack_webhook, data=json.dumps(payload))

    logging.info('Notification sent to Slack!')

def check_loop(feeds, slack_webhook, slack_channel):
    # Create dictionary with time of last item publication for each feed
    last_saved_dates = {}

    # We traverse a copy of feeds, as we might change it in the loop
    for feed in feeds[:]:
        # Fetch feed
        data = fetch(feed)

        # Ignore feed if it's not found
        if data.status != 200:
            logging.warning('Ignoring not existent feed: %s', AWS_RSS_URL % feed)
            feeds.remove(feed)
            continue

        # Get feed's last publication date or set it to START_TIME if no entries
        if data.entries:
            last_saved_dates[feed] = last_pub_date(data)
        else:
            last_saved_dates[feed] = START_TIME

        # Be gentle with Amazon and wait a little between requests
        time.sleep(REQUESTS_INTERVAL)

    # If no feed is left, abort execution
    if not feeds:
        logging.error('No valid feeds left. TIP: Do not specify feeds to watch %s.',
                      AWS_RSS_URL % 'all')
        sys.exit(1)

    # Enter check loop
    logging.info('Entering check loop for following feeds:')
    for feed in feeds:
        logging.info('\tFeed: %s\tLast publication: %s', AWS_RSS_URL % feed, last_saved_dates[feed])

    while True:
        logging.debug('Starting a new check.')
        for feed in feeds:
            # Fetch feed
            data = fetch(feed)

            # Ignore data if doesn't have entries
            if not data.entries:
                logging.debug('Feed without entries: %s.\nData: %s.', feed, data)
                continue

            # Get last publication date
            last_pub = last_pub_date(data)

            logging.debug('Feed: %s\nLast saved date: %s\nLast gotten date: %s',
                          feed, last_saved_dates[feed], last_pub)

            # If content updated, send it to Slack!
            if last_pub > last_saved_dates[feed]:
                send_to_slack(data.entries[0], slack_webhook, slack_channel)

                # Update our dictionary with last publication dates
                last_saved_dates[feed] = last_pub

            # Be gentle with Amazon and wait a little between requests
            time.sleep(REQUESTS_INTERVAL)

        # Wait for the next check
        time.sleep(CHECKS_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poll status from AWS RSS feeds" +
                                                 " and notify changes in Slack.")
    parser.add_argument("slack_webhook",  help="Slack Webhook URL to receive alerts.")
    parser.add_argument("slack_channel",  help="Slack channel to receive alerts.")
    parser.add_argument("feeds", nargs='*', default=['all'],
                        help="List of AWS status RSS feeds you would like to check." +
                             " Just the feed name. For instace, if the RSS link is" +
                             " http://status.aws.amazon.com/rss/all.rss, you just" +
                             " need to input 'all'.")
    args = parser.parse_args()

    check_loop(args.feeds, args.slack_webhook, args.slack_channel)
