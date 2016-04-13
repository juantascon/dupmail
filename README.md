# dupmail

dupmail is a simple, small, lightweight, tool that finds duplicate emails.

## simple

dupmail follows the unix philosophy meaning it only finds duplicate emails, nothing more.
dupmail will never delete emails, you could do this however by piping the output to a simple shell command:

```
dupmail.py /my/maildir --format plain | while read first rest; do rm -rf ${rest}; end
```

## small

dupmail is a single file (~200 loc) python script so you can grab it run it and delete it once your maildir is clean.

## lightweight

Alright I probably lied a little about this point, in reality dupmail is as lightweight as a python script can be. dupmail doesn't store your maildir on memory, it parses emails one by one and keeps only metadata for further processing, this reduces the memory footprint considerably.

On a real case scenario running dupmail on python 3.5.1 against 1.000 emails consumes around 30Mb of memory, in comparison processing 70.000 emails consumes ~150Mb.
