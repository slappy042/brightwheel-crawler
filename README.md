# brightwheel-crawler v2

This python script uses selenium via <https://github.com/ultrafunkamsterdam/undetected-chromedriver> to crawl the page, loads all images, and then passes the auth info to requests and downloads all the image files.

### History

My kid will leave a school that uses the brightwheel app and I wanted to make sure I got all the pictures before he left.

I had an old version I put up never thinking anyone would use it, but I've been thrilled to hear how much use folks are getting out of it enough so that they've opened PRs and issues. Its pretty exciting to see something I threw together when I was really bad at writing code be used and appreciated by others. I've slightly less worse at python than I was when I first wrote this and the Brightwheel page has gotten noteably more reistant to scraping, so I've updated how this works and what it does.

### Future Plans

I _used to_ want to add image recognition to this to be able to parse out my kids face or remove ones that are likely just updates from the school, maybe that will come later. Nowadays, I'm happy to help this keep limping along as long as I have access to the site and can test changes.

### Requirements

1. Python 3.11+ - other versions might work but I am not using them
2. pipenv
3. A brightwheel account with a kid registered

### Installation

1. Clone this repo
2. `pipenv install`
3. `pipenv shell`

### How to use

1. Rename sample-config.yml to config.yml
2. Update config.yml with the proper email and password
3. Update config.yml with the dates your child/ren was/were enrolled and used Brightwheel
4. Run `brightscraper.py -c` to use the undetected chrome driver or `-e` to connect to a debuggable instance of chrome (see <https://github.com/remotephone/brightwheel-crawler/issues/5#issuecomment-1711859342>)
5. Chrome will open and login automatically.
6. You may be prompted for a captcha challenge. If so, I don't think this will work yet and you need to close it out and try again
7. You may be prompte for a 2FA code, enter it reasonably quickly (have your email account ready)
8. If you did not pass an index number for the kid, you will be prompted to select one
9. Wait until the script stops (returns to command prompt) and close Chrome

### Limitations

1. Photos are stored with the raw filename and do not store the date
2. Probably some others, please open an issue

### rename.py

This is a script to get the exifdata from the image and rename the file to be prefixed by the date. This should help sorting them if you do that. You need exiftool installed for it to work. I tried using exifreader and pillow and neither worked for me :shrug:

### rename timestamped files

`https://photo.stackexchange.com/a/126978`

#### Dec 2023
```bash
cd pics
# reads UTC timestamp from filename, puts into standard date tags
exiftool -overwrite_original "-alldates<filename" .

# copies into GPS tags for Google Photos
exiftool -overwrite_original "-GPSTimeStamp<DateTimeOriginal" .
exiftool -overwrite_original "-GPSDateStamp<DateTimeOriginal" .

# timeshift standard date tags to PST
exiftool -overwrite_original "-alldates-=8" .
```

#### Dec 2024
timestamp is in FileModifyDate

```bash
# original from docs
exiftool "-FileName<CreateDate" -d "%Y%m%d_%H%M%S.%%e" DIR

# run this
cp -rp pics pics_test
exiftool "-FileName<FileModifyDate" -d "Ryan_Hardy_%Y%m%d_%H%M%S%%+c.%%e" -globalTimeShift -7 pics_test

```

#### notes for Dec 2024
I ran it in 3 batches then consolidated everything under pics_thru_20241202


# Jeff: overall use

in a terminal:
```bash
google-chrome --remote-debugging-port=9222
```
then [login](https://schools.mybrightwheel.com/sign-in) to brightwheel


in VSCode terminal:
```bash
pipenv install
pipenv shell
python brightscraper.py -e
```

#### July 2025

Chrome now requires `--user-data-dir` for remote-debugging-port to work.

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/home/jeff/.config/google-chrome/Default
```

But now, the brightwheel app has changed how dates are entered so the Selenium code in pic_finder is broken.
Check for any updated forks?
This guy's fork is recent: https://github.com/remotephone/brightwheel-crawler/blob/adb9144cede5b5aa6681a2fb0c0f5a25b99911c9/brightscraper.py
And it uses the Brightwheel API to get a JSON blob with all pic data so there's no Selenium-crawling the feed.
Let's try it!

 