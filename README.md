# about

dupmail is a modern, simple, small, lightweight, tool that finds duplicated emails.

## modern

over the years I've accumulated tons of emails in English, Spanish and Korean.
dupmail was built to support internationalized header values such as: `=?iso-8859-1?q?p=F6stal?=`
and utf-8 encoded headers such as: `pöstal`. If your emails are not utf-8 I highly 
recommend migrating with the any2utf8.sh tool found inside this repo.

## simple

dupmail follows the unix philosophy meaning it only finds duplicated emails, nothing more.
dupmail will never delete emails, however you could do this by piping the output to a simple shell command:

```
dupmail.py /my/maildir | while read first rest; do rm ${rest}; end
```

## small

dupmail is a single file (~300 loc) python script so you can grab it run it and delete it once your maildir is clean.

## lightweight

relatively, in reality dupmail is as lightweight as a python script can be.
dupmail doesn't store your maildir in memory, it parses emails one by one and keeps only metadata for further processing,
this reduces the memory footprint considerably.

running dupmail on a maildir with 1.000 emails uses 30Mb of ram and on a maildir with 70.000 emails it uses 150Mb.

# usage

dupmail works by extracting email metadata, if all fields are the same the emails are considered equal,
you can specify which fields will be extracted by using the `--keys` parameters,
some of the currently available keys include:

  * `body_hash`: sha256 representation of non empty body lines, including attachments
  * `body_size`: total byte size of non empty body lines, including attachments
  * `to`: ordered email address list including To, CC and BCC headers
  * `from`: email address only taken out of From header
  * `date`: Date header formatted as yyyy-mm-dd, time is not included

run `dupmail.py -h` to get the whole list of supported keys

## examples

find emails that are duplicated by `body_hash`, `body_size`, `to` and `from` fields:

`dupmail.py --keys from,to,body_hash,body_size /my/maildir`

