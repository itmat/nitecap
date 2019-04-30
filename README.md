# nitecap
Non-parametric method for identification of circadian behavior

The main functionality is in nitecap.py with the main() function providing a simple interface.

```python
import nitecap
# 6 timepoints, each with 2 replicates. Data is grouped with replicates together and
data = [[5,6, 10,11, 20,21, 15,16,  8, 9, 2,1], # A very cyclic gene with low variance between samples
        [5,9, 10, 4, 20,15,  2, 1, 10,12, 1,5]] # A non-cyclic gene with higher variance between samples
q, td = nitecap.main(data, timepoints_per_cycle = 6,  num_replicates = 2, num_cycles = 1)
# q gives the q-values of the two genes
# td gives the "total_delta" test statistic for each gene (lower is more cyclic)
```


# Setting up the Website on AWS

## Setting up an AWS instance

The instance was set up as an Ubuntu 16.04 image.


## Setting up the website

Note that not every step may be needed here.  In an effort to get things working, some
things may have been done that aren't really necessary.

### Installs

ssh into the AWS instance using the ubuntu login and install the following:

```bash
sudo apt-get update
sudo apt-get install git
sudo apt-get install apache2
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.6
sudo apt-get install emacs
sudo apt-get install sendmail
sudo apt-get install python3.6-venv
sudo apt-get install apache2-dev
sudo apt-get install python3.6-dev
sudo apt-get install r-base
```
Note that the python 3 version that ships with Ubuntu 16.04 is v3.5 and we need v3.6.  The apache version obtained
here is 2.4.18.  

### Setup

Create an ssh key for github using the following instructions:
```
https://help.github.com/articles/connecting-to-github-with-ssh/
```
Since the account is potentially shared, create a config file in the `~/.ssh` directory
as described in this document:
```
https://gist.github.com/jexchan/2351996
```
Set up directories to house the nitecap project and related logs:
```bash
sudo mkdir /var/www/flask_apps
sudo mkdir /var/www/flask_apps/logs
```
I was unable to do a `git clone` directly into `flask_apps` even when I temporarily changed ownership
to `ubuntu:ubuntu`.  Run `git clone git@github.com:tgbrooks/nitecap.git` inside
home directory. Then switch to the development branch
```bash
git checkout develop
```
Create a symbolic link from `/var/www/flask_apps/nitecap` to
the home directory's `nitecap` folder:
```bash
sudo ln -s /home/ubuntu/nitecap /var/www/flask_apps/nitecap
```
Since `www-data` is the account for Apache2, I changed ownership of the `/var/www`
from `root`:
```bash
sudo chown -R www-data:www-data /var/www
``` 
Then inside `/var/www/flask_apps/nitecap`, I created the virtual environment and
populated it. NOTE: try the below without 'sudo' in first command and ommiting the chown, it should hopefully be equivalent.
```bash
sudo python3.6 -m venv venv
source venv/bin/activate
chown -R ubuntu.ubuntu venv
pip install -r requirements.txt
```

Similarly we need to load an R package:
```bash
sudo Rscript -e 'install.packages(c("readr", "stringr"), repos="http://cran.r-project.org")' 
```

Then while activated, I used by mod_wsgi command to grab the configuration data
needed for the apache2.conf site:
```bash
mod_wsgi-express module-config
deactivate
```
The 2 lines obtained must then be added to `/etc/apache2/apache2.conf` just above
the include directive for virtual hosts:
```
# Include generic snippets of statements
IncludeOptional conf-enabled/*.conf

## Add these two lines, which are the output of the `mod_wsgi-express module-config` command
LoadModule wsgi_module "/var/www/flask_apps/nitecap/venv/lib/python3.6/site-packages/mod_wsgi/server/mod_wsgi-py36.cpython-36m-x86_64-linux-gnu.so"
WSGIPythonHome "/var/www/flask_apps/nitecap/venv"

# Include the virtual host configurations:
IncludeOptional sites-enabled/*.conf
``` 
These lines locate the mod_wsgi module and identify the virtual environment to be used.

Then set up the virtual hosts site for nitecap as `nitecap.conf` under
`\etc\apache2\sites-available`:
```
<VirtualHost *:80>

    #ServerName 34.222.252.206 

    ErrorLog /var/www/flask_apps/logs/error.log
    CustomLog /var/www/flask_apps/logs/access.log combined
    LogLevel debug

    WSGIDaemonProcess nitecap user=www-data group=www-data threads=5 home=/var/www/flask_apps/nitecap
    WSGIProcessGroup nitecap
	WSGIApplicationGroup %{GLOBAL}
	WSGIScriptReloading On
    WSGIScriptAlias / /var/www/flask_apps/nitecap/wsgi.py

</VirtualHost>
```
The `LogLevel` setting should probably be raised to `info` in production.  Note that
the `WSGIScriptAlias` maps the server root to an entry point in the `nitecap` folder.
The assumption here is that the entire website is dedicated to this application.  There
may be more configuration here than is actually necessary.

The configuration constants inside the apache2 configurations (e.g., `%{GLOBAL}`
above) need to be populated, which is done as follows:
```bash
source /etc/apache2/envvars
```

# Make and mount volume

On EC2 create a new volume and attach to the instance. It will be located at `/dev/xvdf`. If it is not `xvdf`, run `lsblk` and it will be listed there (probably as the last entry, type `disk` and of the appropriate size).
```bash
sudo mkfs -t ext2 /dev/xvdf
sudo mkdir /mnt/vol1
sudo mount /dev/xvdf /mnt/vol1
sudo mkdir /mnt/vol1/logs
sudo mkdir /mnt/vol1/uploads
sudo mkdir /mnt/vol1/dbs
sudo chown www-data:www-data dbs logs uploads
```
Also need to add the user to the www-data usergroup:
```
sudo usermod -a -G www-data ubuntu
```
NOTE: you must log out and log back in for this to take effect.

# Write .env file
Create the .env file in the nitecap directory, eg:

```
APPLICATION_SETTINGS = "config_default.py"
EMAIL_SENDER =  "admin@nitecap.org"
UPLOAD_FOLDER = "/mnt/vol1/uploads"
DB_BACKUP_FOLDER = '/mnt/vol1/dbs'
DB_BACKUP_LIMIT = 7
SECRET_KEY = "MY_SECRET_KEY"
ANNONYMOUS_EMAIL = "anonymous@upenn.edu"
ANNONYMOUS_PWD = "MY_ANONYMOUS_PASSWORD"
SMTP_SERVER_HOST = '127.0.0.1'
DATABASE_FILE = "nitecap.db"
LOG_FILE = "/mnt/vol1/logs/nitecap.log"
LOG_LEVEL = "INFO"
```

# Networking

You must enable the correct ports in AWS EC2 dashboard.
You can configure this under Security Groups.
For inbound traffic, we have enabled ports 80, 22, 25, 465, 443 for HTTP, SSH, SMTP, SMTPS, and HTTPS, respectively with source ::/0.
All outbound traffic is allowed.

# Execution
Enable the nitecap virtual host and disable the default virtual host:
```bash
sudo a2ensite nitecap.conf
sudo a2dissite 000-default.conf
```
Ensure that the apache2 configuration has no syntax errors (it may complain
about not finding a FQDN server name, but that's OK for now).
```bash
apache2ctl configtest
```
If you receive an error about `AH00557: apache2: apr_sockaddr_info_get() failed for ip-######`, add a line to /etc/hosts that is `127.0.0.1 ip-######` where ip-####### is from the error message before.

Start the apache2 service:
```bash
sudo service apache2 start
```
Try to access the site at `http://34.222.252.206/` currently the route redirects
to the `http://34.222.252.206/load_spreadsheet` page.  If problems occur, tail the
logs for apache2 at `\var\log\apache2` and for the site itself at
`\var\www\flask_apps\logs`.  The `error.log` contains more the errors.  The
`access.log` only reports requests and responses.  You can also check to make sure that 
apache2 loaded the wsgi module:
```bash
apache2ctl -t -D DUMP_MODULES
```

Note that, as of this writing, the uploads folder and the link emailed to users upon
reqistration are both hard-coded.  They need to be moved into a configuration file.  For
now the uploads folder was changed in `app.py` as follows:

```python
UPLOAD_FOLDER = '/mnt/vol1/uploads'
ALLOWED_EXTENSIONS = set(['txt', 'csv', 'xlsx'])
```
The emailed link was changed in the `user.py` module as follows:
```python
 def send_confirmation_email(self):
        email = EmailMessage()
        email['Subject'] = 'User registration confirmation for Nitecap access'
        email['From'] = 'put a real address here'
        email['To'] = self.email
        email.set_content(f'Please click on this link to confirm your registration. http://34.222.252.206/confirm_user/{self.id}')
        s = smtplib.SMTP(host='127.0.0.1', port=25)
        #s.starttls()
        #s.login('you@gmail.com', 'password')
        s.send_message(email)
        s.quit()
```
The `starttls()` statement is commented out since leaving it in place results in an exception: 
`STARTTLS extension not supported by server`.  I suppose this is because we are not currently running
SSL but I don't know for sure.  The port we are using for mail (25) is not secure.  Another change to
hardcoding above was the sender address.  A fake address did not work.

To restart the server after a code change run
```python
sudo service apache2 restart
```
