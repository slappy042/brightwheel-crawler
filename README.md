# brightwheel-crawler v3

Fork of [brightwheel-crawler](https://github.com/remotephone/brightwheel-crawler)

This python script uses selenium via <https://github.com/ultrafunkamsterdam/undetected-chromedriver> to log into Brightwheel, then use the API urls to get parent and child IDs.  IDs are used to fetch "ac_photo" activities for each child during the timeframe specified.

Photos are saved to pics folder with child's first name, the activity (aka "event date") and the photo database object ID.  This should ensure uniqueness and orderability.

EXIF data is added to the image

- "Artist" is the actor (teacher) name
- "ImageDescription" is the activity note
- "DateTimeOriginal" is the activity created_at datetime

## Requirements

1. Python 3.11+ - other versions might work but I am not using them
2. pipenv
3. A brightwheel account with a kid registered

## Installation

1. Clone this repo
2. `pipenv install`
3. `pipenv shell`

## How to use

1. Rename sample-config.yml to config.yml
2. Update config.yml with the proper email and password
    1. Optional-Provide the parent and child IDs (the really long UUID's) if you know them
3. Update config.yml with the dates your wish to search
4. Run `brightscraper.py -c` to use the undetected chrome driver or `-e` to connect to a debuggable instance of chrome (see <https://github.com/remotephone/brightwheel-crawler/issues/5#issuecomment-1711859342>)
5. Chrome will open and login automatically.
6. You may be prompted for a captcha challenge. If so, I don't think this will work yet and you need to close it out and try again
7. You may be prompte for a 2FA code, enter it reasonably quickly (have your email account ready)
8. If you did not pass an index number for the kid, photos for each kid will be downloaded.  Ignore if you have one kid enrolled
9. Wait until the script stops (returns to command prompt) and close Chrome

### Limitations

1. With some additional work, could be fully automated to get 2FA code from email
2. Some issues with Chrome driver, currently set to use version 127, but only because of issues I had with latest version being changed during development
3. Requires Selenium to navigate.  I tried hitting API's directly through requests package, but was detected as a bot
4. Did not test with Mac OS or Linux

## Resources

[Driver issues](https://stackoverflow.com/questions/29858752/error-message-chromedriver-executable-needs-to-be-available-in-the-path/52878725#52878725)
[piexif with Pillow](https://piexif.readthedocs.io/en/latest/sample.html#with-pil-pillow)
