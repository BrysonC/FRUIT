# FRUIT = FIRST Robotics Uploader from an Indiana Teammate
A python script (with GUI) for the automated processing of (long) livestream recordings into (short) match videos.

## How it works
1. Gets information about the matches from FIRST, includes start time and score post time
2. Splits the livestream recording into chucks based on those start & post times
3. Combines those chunks together into match videos
4. Generates a thumbnail using the match number and teams involved
5. Uploads the videos to YouTube
6. Notifies The Blue Alliance of the videos

## Upcoming Features
- [x] Blue Alliance Support
- [X] Use Twitch instead of a file for input
- [ ] Load a past CONFIG to save on input time
- [ ] Better handling of erroneous inputs
- [ ] Update up from Python 3.12.2
- [ ] Cool logo

## Setup for Developers; Getting FRUIT Running 
1. Download and setup Python 3/Virtual Environment on IDE of choice
2. Install required packages; see "requirements.txt"
3. Add file "client_secrets" to TOOLS folder; take code from example.client_secrets and fill empty quotation marks with correct information
4. Add file "CREDENTIALS" to main folder; copy code from example.CREDENTIALS

## Setup for Developers; Operating FRUIT
1. Follow https://github.com/purduefirst/FRUIT/wiki/APIs and register for desired API keys 
2. Fill empty credentials fields with API information; in FRUIT or in the code
3. Input correct Season Year and Event Code in the event info tab of FRUIT; no event name needed
4. To connect to Youtube, access is needed from Bryce Castle: email castle5@purdue.edu

## To add (notes for myself)
1. do i tell users to get the client_secrets hidden fields from bryce? how else can they obtain them?


