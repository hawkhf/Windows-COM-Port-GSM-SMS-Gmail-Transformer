from __future__ import print_function
import smtplib, ssl
import os
from gsmmodem.modem import GsmModem, SentSms
import email
import imaplib
from cryptography.fernet import Fernet
import find_coms
import threading
from email.mime.text import MIMEText
import html2text
import time
import datetime

# Defines list for read_conf and conf functions
variable_lst = []


class GlobalVal:
    def __init__(self, working_dir, slash_var):
        # Using the 'conf' function, assign values from conf.txt, you can find descriptions of the variables there
        self.working_dir = working_dir
        self.slash_var = slash_var
        self.opsys = conf("opsys").lower()
        self.sender_pass = bytes(conf("sender_pass") + "=", "utf-8")
        self.message_print_length = conf("message_print_length")
        self.status_interval = conf("status_interval")
        self.birthday = conf("birthday")
        self.today = datetime.datetime.today().strftime("%d-%m")

        # Gsm modem vars
        self.BAUDRATE = conf("BAUDRATE")

        # Email service (read and write) vars
        self.ssl_port = conf("ssl_port")
        self.sender_email = conf("sender_email")
        self.SERVER = conf("SERVER")
        self.context = ssl.create_default_context()
        self.imap_mail_instance = None
        self.mail_thread = None
        self.mail_exception_flag = True

        # Phone number length and country code
        self.CODE = conf("CODE")
        self.LENGTH = conf("LENGTH")

        # Values for limiting daily sms traffic, safety feature to avoid accidental "fun"
        self.interval = conf("interval")
        self.interval_counter = 0
        self.sms_limit = conf("sms_limit")
        self.sms_counter = 0
        self.sms_counter_reset = 86400/self.interval

        # Admin information
        self.admin_name = conf("admin_name")
        self.admin_email = conf("admin_email")
        self.admin_phone_num = conf("admin_phone_num")

        # Not to be touched
        self.var0 = b'qHKP1WZk5yxU4uW3ktNLlzwHLFuSwzRExe4_yj3VolY='


# creates the User class, used to map/reference user data
class User:
    """ This class is used to globally track and reference user data """
    # Important adding anything new will require a change in the "read_userdata" function
    # user_lst = [User(usr_data_lst[i][0], usr_data_lst[i][1], usr_data_lst[i][2], usr_data_lst[i][3],
    # usr_data_lst[i][4]) for i in range(len(usr_data_lst))]
    _registry = []

    def __init__(self, name, phone_num, pin, sim_num, birthday, email_lst, contact_dic):
        self._registry.append(self)
        self.name = name
        self.phone_num = phone_num
        self.pin = pin
        self.email_lst = email_lst
        self.email = email_lst[0]
        self.sim_num = sim_num
        self.birthday = birthday
        self.port = None
        self.instance = None
        self.thread = None
        self.modem_flag = False
        self.sms_cat_str = ""
        self.contact_dic = contact_dic


def read_conf():
    """ Reads data from the conf.txt file"""

    rough_var_lst = []
    working_dir = os.getcwd()
    slash_var = ""

    # Determines which path delimiter should be used when opening files
    if "\\" in working_dir:
        slash_var = "\\"
    elif "/" in working_dir:
        slash_var = "/"
    else:
        message_print("Error! Problem occurred locating current working directory!")
    try:
        with open(working_dir + slash_var + "conf.txt", "r") as conf_txt:
            conf_txt.seek(0)
            conf_lines = conf_txt.readlines()
            conf_txt.close()
    except FileNotFoundError:
        error_text = "File \"conf.txt\" was not found"
        message_print(error_text)


    # Looks at the contents of the conf.txt file line by line.
    # Sorts out all the comment lines.
    # Splits the variable value paris, 'os = windows' becomes ['os', 'windows']
    for i in conf_lines:
        if i[0] != "#":
            mini_lst = i.split("=")
            rough_var_lst.append(mini_lst)

    # takes the rough list of variable/value pairs and strips any erroneous spaces
    for i in rough_var_lst:
        for x in i:
            variable_lst.append(str(x).strip())
    return working_dir, slash_var


def read_userdata():
    """ This function creates 'User' class objects from the information pulled from userdata.txt"""
    # opens and reads userdata.txt, creates list usr_lines

    usr_data_lst = []

    try:
        with open(value.working_dir + value.slash_var + "userdata.txt", "r") as usr_txt:
            usr_txt.seek(0)
            usr_lines = usr_txt.readlines()
            usr_txt.close()
    except FileNotFoundError:
        error_text = "File \"userdata.txt\" was not found"
        message_print(error_text)
        exit(FileNotFoundError)

    # Turns usr_lines into a list of lists called usr_data_lst also sorts out all the comment lines
    # user_counter keeps track of the total user count
    for i in usr_lines:

        if i[0] == "#":
            pass

        elif "@" in i:
            mail_lst = i.split(",")

            for i in range(len(mail_lst)):
                mail_lst[i] = mail_lst[i].strip()

            usr_data_lst[-1].append(mail_lst)

        elif ":" in i:
            usr_data_lst[-1].append(eval(i))

        else:
            contact_lst = i.split(",")

            for i in range(len(contact_lst)):
                contact_lst[i] = contact_lst[i].strip()

            usr_data_lst.append(contact_lst)

    # Adds all the users to the user class, not proud of this solution, but it works.
    # Will need to be changed if more user attributes are added
    [User(usr_data_lst[i][0].strip(), usr_data_lst[i][1].strip(), usr_data_lst[i][2].strip(),
          usr_data_lst[i][3].strip(), usr_data_lst[i][4], usr_data_lst[i][5], usr_data_lst[i][6]) for i in range(len(usr_data_lst))]

    for user in User._registry:
        for i in range(len(user.email_lst)):
            user.email_lst[i] = user.email_lst[i].strip()


def read_portdata():
    """ Maps each user in the 'User' class registry to the correct modem serial port based on ICCID number.
     Updates User's self.port attribute"""

    # needs error handling!
    port_list = []
    port_sim_num_dic = {}

    # Creates a list of open serial ports, operating system dependent.
    if value.opsys == "windows":
        port_list = find_coms.fetch_coms_win()

    elif value.opsys == "linux":
        port_list = find_coms.fetch_coms_lin()

    else:
        error_text = "os configuration in conf.txt is incorrect or missing!"
        message_print(error_text)
        exit()

    # Tries to map open serial ports to the sim number. Connects to each attached modem and requests ccid number
    # Desperately needs better error handling
    for port in port_list:
        message_print(title_str=("Connecting to {}".format(port)))

        # Creates a GsmModem object for each serial port in port list
        sim_test = GsmModem(port, value.BAUDRATE, smsReceivedCallbackFunc=handle_sms)

        # Tries to contact the modem and request the iccid number of the inserted sim card
        try:
            # The 'iccid()' is something I had to make to communicate with modems before providing the pin
            ccid = sim_test.iccid()

            # Adds ccid/ serial port value pairs to the port_sim_num dictionary
            port_sim_num_dic[ccid] = port
        except Exception as e:
            message_print("Exception occurred connecting to serial port", ("Exception: " + str(e), ))

        sim_test.close()

    # Checks to see if any valid ports where found
    if len(port_sim_num_dic) == 0:
        error_text = "Could not open any ports!"
        message_print(error_text)
        exit()

    debug = ""
    try:
        # Tries to update the self.port attribute of every user in the 'User' registry
        # By using their self.sim_number as a key for the port_sim_num dictionary
        for user in User._registry:
            debug = user.name
            user.port = port_sim_num_dic[str(user.sim_num).strip()]

    except KeyError:
        error_text = "User sim ICCID: '{}' Does not match any detected sim.".format(str(debug))
        message_print(error_text, ("Check that userdata.txt information is correct!", ""))
        exit()


def hidden():
    return Fernet(value.var0).decrypt(value.sender_pass).decode()
    pass


def conf(var):
    """Called to fetch values from the 'variable_lst' created by the 'read_conf()' function.
    Takes a string as input and returns matching value"""

    conf_val = ""
    try:
        # Finds the string 'var' in the variable list, values in the variable_lst are paired together.
        # The value that 'var' corresponds with will be in the next index, hence the +1
        var_index = variable_lst.index(var) + 1

        # Assigns the value corresponding with 'var'
        conf_val = str(variable_lst[var_index]).replace(" ", "")
    except IndexError:
        message_print(title_str=("Variable {} does not appear in conf.txt".format(var)))

    # Tries to covert the string value into an integer, if that fails, tries to covert it into a float

    if conf_val.lower() == "true":
        conf_val = True
        return conf_val

    if conf_val.lower() == "false":
        conf_val = False
        return conf_val

    try:
        conf_val = int(conf_val)
    except ValueError:
        pass
        try:
            conf_val = float(conf_val)
        except ValueError:
            pass

    return conf_val


def send_mail(subject, message, receiver_email):
    text_type = 'plain'
    text = message + "\n\n\nThis message was sent by Hawk's SMS bot.\n" \
                     "For more information send me an email with the subject \"help\""
    msg = MIMEText(text, text_type, 'utf-8')
    msg['Subject'] = subject
    msg['From'] = value.sender_email
    msg['To'] = receiver_email

    with smtplib.SMTP_SSL("smtp.gmail.com", value.ssl_port, context=value.context) as server:
        server.login(value.sender_email, hidden())
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        message_print(title_str=("Email Sent to: {}".format(msg['To'])))


def handle_sms(modem, sms):
    user = ""

    for i in User._registry:
        if i.instance == modem:
            user = i
    if user == "":
        message_print("Error instance and modem don't match!")
        exit()

    message_print("SMS Received", (user.name, sms.number, sms.text, sms.time), user)

    sms_number = sms.number

    for i in range(len(user.contact_dic)):
        if list(user.contact_dic)[i] in sms_number:
            sms_number = list(user.contact_dic.values())[i]

    if len(sms.text) < 60:
        subject = "SMS From: {}".format(sms_number)
        message = "{}\nMessage from:{}\n{}\n\n" \
                  "{}\nMessage reads:{}\n{}\n\n " \
                  "Received: {} \n\n " \
                  "This email is from Hawk's sms bot"\
            .format(("-"*20), sms.number, ("-"*20), ("-"*20), sms.text, ("-"*20), sms.time)
        receiver_email = user.email
        send_mail(subject=subject, message=message, receiver_email=receiver_email)
    else:
        user.sms_cat_str += sms.text
        cat_thread = threading.Thread(target=sms_concatenation, args=(user, sms.number, sms.time))
        cat_thread.run()


def sms_concatenation(user, number, time_stamp):
    time.sleep(2)
    if user.sms_cat_str == "":
        return

    subject = "SMS From: {}".format(number)
    message = "{}\nMessage from:{}\n{}\n\n" \
              "{}\nMessage reads:{}\n{}\n\n " \
              "Received: {} \n\n " \
              "This email is from Hawk's sms bot" \
        .format(("-" * 20), number, ("-" * 20), ("-" * 20), user.sms_cat_str, ("-" * 20), time_stamp)
    receiver_email = user.email
    send_mail(subject=subject, message=message, receiver_email=receiver_email)


def connect_modem(user):
    message_print("Initializing {}'s modem".format(user.name),
                  ("Port: {}".format(user.port), "PIN: {}".format(user.pin)))
    # Uncomment the following line to see what the modem is doing:
    # logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
    user.instance = GsmModem(user.port, value.BAUDRATE, smsReceivedCallbackFunc=handle_sms)


    # This is in reference to what kind of message data you intend to send to the modem, False = normal strings.
    user.instance.smsTextMode = False
    user.instance.connect(str(user.pin))
    message_print("Waiting for SMS message on {}'s modem".format(user.name), ("Port: {}".format(user.port), ""))
    user.instance.processStoredSms(unreadOnly=True)
    try:
        # Specify a (huge) timeout so that it blocks for a long time, but still receives CTRL+C interrupt signal
        # Not best practice, since threads will stay alive even if main crashes. The machine must then be booted.
        user.instance.rxThread.join(2 ** 20)

    finally:
        user.instance.close()
        message_print(title_str=("{}'s Modem Thread died".format(user.name)))
        user.thread = threading.Thread(target=connect_modem, args=(user, ))
        user.thread.start()


def send_sms(user, destination, message=""):
    response = ""

    if value.sms_counter > value.sms_limit:
        error_text = "Outgoing SMS traffic has exceeded the limit!"
        # handle_errors(error_text)
        exit()

    e = ""

    try:
        response = user.instance.sendSms(destination, message, True)
    except Exception as e:
        message_print("Exception when sending SMS", ("Exception: " + str(e),
                                                     "Sender: " + user.name,
                                                     "Destination: " + destination))

    if e == "":
        if type(response) == SentSms:
            subject = "SMS to '{}' has been successfully delivered".format(str(destination))
            email_message = "Your message:\n{}\nhas been successfully delivered to {}".format(message, str(destination))
            send_mail( subject, email_message, user.email)
            message_print(title_str=("SMS from {} Delivered to {}".format(user.name, destination, user)))
        else:
            e = None

    if e != "":
        subject = "SMS to '{}' could not be sent".format(str(destination))
        email_message = "Your message:\n{}\ncould not be sent to {}" \
                        "\n\nCheck that the phone number is correct\n\n" \
                        "Contact {} for help/more information\nAdmin e-mail: {}"\
            .format(message, str(destination),value.admin_name, value.admin_email)
        send_mail(subject, email_message, user.email)
        message_print(title_str=("SMS from {} Could not be sent to {}".format(user.name, destination, user)))


def mail_setup():
    """Reads emails from the email address specified in the conf.txt file
    """
    if value.mail_exception_flag is True:
        time.sleep(1)
        value.mail_exception_flag = False


    # connect to the server and go to its inbox
    value.imap_mail_instance = imaplib.IMAP4_SSL(value.SERVER)
    value.imap_mail_instance.login(value.sender_email, hidden())
    message_print("Logged into email")

    # Starts mail thread
    value.mail_thread = threading.Thread(target=check_inbox)
    value.mail_thread.start()


def check_inbox():
    """ Periodically checks the inbox of the attached 'sender_email' account. Takes the imaplib object from
    read_mail_setup as argument. Also resets the sms limiter roughly every day"""

    time.sleep(value.interval)

    try:

        # Increments the interval counter, this is used to reset the sms limiter roughly every day
        value.interval_counter += 1

        if value.interval_counter % 900 == 0:
            mail_setup()

        # Checks to see if the interval counter has exceeded the reset value, if so the counters are reset
        if value.interval_counter > value.sms_counter_reset:
            value.interval_counter = 0
            value.sms_counter = 0


        # we'll search using the unseen criteria to retrieve
        # every unseen message inside the inbox
        # it will return with its status and a list of ids

        value.imap_mail_instance.select('inbox')

        # the list returned is a list 'data' of bytes separated
        # by white spaces on this format: [b'1 2 3', b'4 5 6']
        status, data = value.imap_mail_instance.search(None, '(UNSEEN)')

        mail_ids = []

        # Goes through the 'data' list splitting its block of bytes and appending to the mail_ids list
        for block in data:
            mail_ids += block.split()

        # Fetches the email corresponding to every id to extract its content
        for i in mail_ids:
            status, data = value.imap_mail_instance.fetch(i, '(RFC822)')

            # Sends the mail data to be interpreted by the 'email2_text()' function
            msg = email2_text(data[0][1])

            message_print("Email Received", (msg["subject"], msg["date"], msg["from"], msg["body"]))

            # Sends the interpreted mail data to the email_handling function
            handle_email(msg["subject"], msg["date"], msg["from"], msg["body"])


        # Gives the status function a chance to check the email service
        if value.mail_exception_flag is True:
            time.sleep(1)

        # Returns if the exception is still true
        if value.mail_exception_flag is True:
            return
        else:
            check_inbox()

    except Exception as e:
        message_print("Exception when checking inbox email", ("Exception: " + str(e), ""))
        value.mail_exception_flag = True
        mail_setup()


def handle_email(subject, date, from_address, body):
    subject = subject.lower()
    user = ""
    from_address = from_address.split(" ")
    for i in from_address:
        if "@" in i:
            from_address = i.replace(" ", "")
            break

    for user_object in User._registry:
        for address in user_object.email_lst:
            if address in from_address:
                user = user_object
                message_print(title_str=("User found: {}".format(user.name)))
            break

    if value.admin_email in from_address:
        admin_command(subject)
        return

    if user == "":
        message_print("Unknown address")
        return

    subject = subject.replace(" ", "")
    for i in range(len(user.contact_dic)):
        if list(user.contact_dic.values())[i].lower() in subject.lower():
            subject = list(user.contact_dic)[i]

    destination = ""
    for i in subject:
        try:
            int(i)
            destination += i
        except ValueError:
            pass
    try:
        int(destination)
        send_sms(user, str(destination), str(body))
    except ValueError:
        user_command(user, subject, body)
        message_print("No destination number. Checking for commands")
        pass


def user_command(user, subject, body):
    commands = "User Command: " + subject
    outputs = "Body: " + body + "\n"

    if "help" in subject or "hjelp" in subject:
        subject_line = "Hey {}! I see that you have asked for help!".format(user.name)
        message = "The way this works is actually pretty straightforward.\n\n" \
                  "RECIVING SMS:\n" \
                  "Any SMS sent to your Norwegian phone number: {} " \
                  "will be packaged and sent to your via your email address: {}\n\n" \
                  "SENDING SMS:\n" \
                  "If you want to send a SMS with your norwegian number you can do so by sending an email to this" \
                  " address: {}.\n\nThe subject line must contain the phone number you wish to send the SMS to " \
                  "(international numbers are supported, however sending to them is rather expensive).\n" \
                  "*How the number is formatted is irrelevant as long " \
                  "as all of the digits appear in the correct order.\n " \
                  "Example: +47 92 (Message to Hawk) 43 49 41\n" \
                  "Example: 92434941\n\n" \
                  "The body of the email will become the contents of your text message.\n Don't add anything here that" \
                  "you don't want to appear in the text message.\n" \
                  "There is no support of attachments, images or gifs. Most emojis should work.\n" \
                  "Example: Hawk is the best\n\n" \
                  "You will receive conformation by email if your sms was sent properly\n\n" \
                  "UPDATING CONTACTS:\n" \
                  "By sending an email to smsbot you can create a list of contacts.\n" \
                  "The subject line needs to include \"contact\"" \
                  "The body of the email should look as follows:" \
                  "38449398 = the bank\n" \
                  "93484901 = my freind from school\n" \
                  "Number first, the \"=\" then name then a new line\n" \
                  "*1 If you have set up contacts you can now send sms using the contact name instead of the number.\n" \
                  "CHECKING YOUR INFORMATION:\n" \
                  "By sending an email to smsbot you can retrieve you user information.\n" \
                  "The subject line needs to include \"info\"\n\n" \
                  "RETRIEVING MESSAGE LOGS:\n" \
                  "By sending an email to smsbot you can retrieve your message log files.\n" \
                  "The subject line needs to include \"log\"." \
                  "It can also include the four digit year YYYY as argument, as of now new message log files are created once a year\n\n" \
                  "Note! Please double check that the number you enter in the" \
                  " subject-line is valid and input correctly.\n" \
                  "Invalid numbers are known to cause serious performance issues.\n" \
                  "If you need clarification or have any questions contact {} for help/more information\n" \
                  "Admin e-mail: {}".format(user.phone_num, user.email, value.sender_email, value.admin_name, value.admin_email)
        send_mail(subject=subject_line, message=message, receiver_email=user.email)
        outputs += "Help: Email sent\n"
        return

    if "info" in subject:
        subject_line = "Hey {}! Here is all of the information I have about you!".format(user.name)
        email_str = ""
        contact_str = ""

        for i in range(len(user.contact_dic)):
            contact_str += list(user.contact_dic)[i] + " = " + list(user.contact_dic.values())[i] + "\n"

        for i in user.email_lst:
            email_str += i + "\n"

        message = ("-"*30) + "\n" + \
                             "User Information:\n" + \
                  ("-"*30) + "\n" +\
                             "Name: {}\n" \
                             "Phone Number: {}\n" \
                             "Sim Card ICCID Number: {}\n" \
                             "Emails:\n" \
                             "{}\n" \
                             "Preferred Email: {}" \
                             "Contacts:\n" \
                             "{}\n" +\
                  ("-"*30) + "\n" + \
                             "Technical Information:\n" + \
                  ("-"*30) + "\n" + \
                             "Port: {}\n" \
                             "Instance: {}\n" \
                             "Thread: {}\n".format(user.name, user.phone_num, email_str, user.email
                                                   , user.port, user.instance, user.thread)

        send_mail(subject=subject_line, message=message, receiver_email=user.email)
        outputs += "Information: Email sent"
        return

    if "contact" in subject:
        subject_line = "Hi, I see you are trying to update your contacts!"

        body = body.strip()
        body_lst = body.split("\n")

        message = "Here is what I received:\n" + body + "Here are the results: "

        for i in range(len(body_lst)):
            body_lst[i] = body_lst[i].split("=")

        if len(body_lst) == 0:
            outputs += "No contacts found\n"

        message += "New contact:\n"
        outputs += "New contact:\n"
        for i in body_lst:
            try:
                int(i[0].strip)
                user.contact_dic[i[0].strip()] = i[1].strip()
                outputs += str(i) + "\n"
            except ValueError:
                message += "Invalid contact input\n"
                outputs += "Invalid contact input\n"

        try:
            with open(value.working_dir + value.slash_var + "userdata.txt", "r") as usr_txt:
                usr_txt.seek(0)
                usr_lines = usr_txt.readlines()
                usr_txt.close()
        except FileNotFoundError:
            error_text = "File \"userdata.txt\" was not found"
            message_print(error_text)
            exit(FileNotFoundError)

        for i in range(len(usr_lines)):
            if user.name in usr_lines[i] and user.sim_num in usr_lines[i]:
                usr_lines[(i + 2)] = str(user.contact_dic) + "\n"

        try:
            with open(value.working_dir + value.slash_var + "userdata.txt", "w") as usr_txt:
                # with open(value.working_dir + value.slash_var + "userdata.txt", "r") as usr_txt:
                usr_txt.seek(0)
                usr_txt.writelines(usr_lines)
                usr_txt.close()
        except FileNotFoundError:
            error_text = "File \"userdata.txt\" was not found"
            message_print(error_text)
            exit(FileNotFoundError)
        message += "All newly identified Contact have been added!\n"
        outputs += "Contact added\n"
        send_mail(subject=subject_line, message=message, receiver_email=user.email)

    if "log" in subject:
        year = ""
        for i in body:
            try:
                int(i)
                year += i
            except ValueError:
                pass
        if year == "":
            year = datetime.datetime.today().strftime("%Y")
        name_year = user.name + "-" + year
        subject_line = "Hi, I see you are requesting log data!"

        message = "Here is the log data I have from year {}:\n".format(year)
        log_str = ""
        filename = name_year + ".txt"
        try:
            with open(value.working_dir + value.slash_var + filename, "r") as log_txt:
                log_txt.seek(0)
                log_str = log_txt.read()
                log_txt.close()
        except FileNotFoundError:
            message += "Doesn't look like I have any log data from {}!".format(year)
            outputs += "Log file \"{}\" was not found".format(filename)
        message += log_str
        send_mail(subject=subject_line, message=message, receiver_email=user.email)

    if outputs == ("Body: " + body + "\n"):
        message_print("No commands found")
        return

    else:
        message_print(commands, (outputs, ""))
        return


def admin_command(subject):
    """Tool that allows for admin to send certain commands to server remotely via the email_handling function.
    Parses string argument.
    test -: Sends a test sms from users to the admin phone number, takes argument "all" or user phone numbers
    separated by commas
    """

    # Remove spaces in input string
    subject = subject.replace(" ", "")
    subject = subject.lower()

    # Looks for "test -" command in string
    if "test-" in subject:

        # Determines if any user numbers or "all" are in the string
        for user in User._registry:
            if str(user.phone_num) in subject or "-all" in subject:
                message = "This is a test message from {}'s number: {}".format(user.name, user.phone_num)

                # sends a sms to the admin phone number
                send_sms(user, str(value.admin_phone_num), message)
                return

    # Looks for "info"
    if "info-" in subject:
        message = ("-" * 20) + "\n"

        # Determines if any user names or "-all" are in the string
        for user in User._registry:
            if str(user.name).lower() in subject or "all" in subject:
                message += "Name: {}\nPhone Number: {}\nPin: {}\n" \
                           "Email: {}\nSim Number: {}\nPort: {}\n" \
                           "Instance: {}\nThread: {}\nModem Signal strength: {}\n\n{}\n".format(
                            user.name, user.phone_num, user.pin, user.email,
                            user.sim_num, user.port, user.instance, user.thread,
                            user.instance.signalStrength, ("-" * 20))

        mail_sub = "User Information"

        # sends an email to the admin email address
        send_mail(mail_sub, message, value.admin_email)
        return

    if "status" in subject:
        status(return_mail=True)


def email2_text(rfc822mail):
    # parse the message
    msg_data = email.message_from_bytes(rfc822mail, policy=email.policy.default)

    mail_value = {"from": header_decode(msg_data.get('From')),
                  "date": header_decode(msg_data.get('Date')),
                  "subject": header_decode(msg_data.get('Subject')),
                  "body": ""}

    # Get From, Date, Subject

    # Get Body
    if msg_data.is_multipart():
        for part in msg_data.walk():

            ddd = msg2body_text(part)
            if ddd is not None:
                mail_value["body"] = mail_value["body"] + ddd
                break
    else:

        ddd = msg2body_text(msg_data)
        mail_value["body"] = ddd

    return mail_value


# get body text from a message (EmailMessage instance)
def msg2body_text(msg):
    ct = msg.get_content_type()
    cc = msg.get_content_charset()  # charset in Content-Type header
    cte = msg.get("Content-Transfer-Encoding")

    # skip non-text part/msg
    if msg.get_content_maintype() != "text":
        return None

    # get text
    ddd = msg.get_content()

    # html to text
    if msg.get_content_subtype() == "html":
        try:
            ddd = html2text.html2text(ddd)
        except:
            print("error in html2text")
    return ddd


def header_decode(header):
    hdr = ""
    for text, encoding in email.header.decode_header(header):
        if isinstance(text, bytes):
            text = text.decode(encoding or "us-ascii")
        hdr += text
    return hdr


def message_print(title_str="", item_tup=None, user=None):
    log_str = ""

    if title_str == "" and item_tup is None:
        print("\n" + "-" * value.message_print_length + "\n")

    else:
        str_length = len(title_str)
        multiplier = (int(value.message_print_length) - int(str_length)) // 2
        multiplier -= 1
        string = ("\n" + ("-" * multiplier) + " " + title_str + " " + ("-" * multiplier) + "\n")
        print(string)
        log_str += string

    if item_tup is None:
        return

    for i in item_tup:
        print(i)
        log_str += str(i) + "\n"

    print("\n" + "-" * value.message_print_length + "\n")
    log_str += "\n" + "-" * value.message_print_length + "\n"

    logging(log_str, user)


def logging(log_str, user=None):
    date = datetime.datetime.today()
    week = str(date.isocalendar()[1]) + "-" + str(datetime.datetime.today().strftime("%Y"))
    filename = week + ".txt"
    log_str = "\n{}:\n{}".format(date, log_str)
    try:
        with open(value.working_dir + value.slash_var + filename, "a") as log_txt:
            log_txt.write(log_str)
            log_txt.close()

    except FileNotFoundError:
        error_text = "File \"{}\" was not found".format(filename)
        message_print(error_text)

        with open(value.working_dir + value.slash_var + filename, "w") as log_txt:
            message_print("New log file \"{}\" has been writen")
            log_txt.write(log_str)
            log_txt.close()

    if user is None:
        return

    name_year = user.name + str(datetime.datetime.today().strftime("%Y"))
    filename = name_year + ".txt"
    try:
        with open(value.working_dir + value.slash_var + filename, "a") as log_txt:
            log_txt.write(log_str)
            log_txt.close()

    except FileNotFoundError:
        error_text = "File \"{}\" was not found".format(filename)
        message_print(error_text)

        with open(value.working_dir + value.slash_var + filename, "w") as log_txt:
            message_print("New log file \"{}\" has been writen")
            log_txt.write(log_str)
            log_txt.close()


def date_check():
    date = datetime.datetime.today()
    date_str = date.strftime("%d-%m")

    if value.today == date_str:
        return
    else:
        value.today = date_str

    tomorrow = date + datetime.timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%d-%m")

    if "01-" in date_str:
        admin_command("test -all")

    for user in User._registry:
        if str(user.birthday) in date_str:
            with open(value.working_dir + value.slash_var + "bday.txt", "r", encoding="utf8") as bday_txt:
                bday_str = bday_txt.read()
                bday_txt.close()

            subject = "Happy Birthday {}!".format(user.name)
            message = "Couldn't help but notice that it was your birthday today! Let me sing you a song!\n\n" \
                      "Happy birthday to you, happy birthday to you!\n" \
                      "You look like a monkey, and you smell like one too!\n\n\n"
            message += bday_str
            send_mail(subject, message, user.email)

        if str(user.birthday) in tomorrow_str:
            subject = "Hey, it's {}'s birthday tomorrow!"
            message = ""
            send_mail(subject, message, value.admin_email)


def status_thread():
    for i in range(900):
        status(return_mail=False, break_flag=False, recursion_break=False)
        time.sleep(value.status_interval)
    status(return_mail=False, break_flag=False, recursion_break=True)


def status(return_mail=False, break_flag=False, recursion_break=False):

    if recursion_break is True:
        status_thr = threading.Thread(target=status_thread)
        status_thr.start()

    date_check()
    modem_exception_flag = False

    title_str = "Status Report"
    services_str = ""
    value.mail_exception_flag = True
    try:
        services_str += "Checking Email Service:\n"
        lst = value.imap_mail_instance.list()
        if lst:
            services_str += "Running\n"
        value.mail_exception_flag = False

    except Exception as e:
        services_str += "Exception checking inbox email: {}\n".format(str(e))
        value.mail_exception_flag = True

    for user in User._registry:
        user.modem_flag = True
        try:
            services_str += "\nChecking {}'s modem:\n".format(user.name)
            signal_strength = str(user.instance.signalStrength)
            services_str += "Running\nSignal Strength: " + signal_strength
        except Exception as e:
            services_str += "Exception checking {}'s modem: {}\n".format(user.name, str(e))
            user.modem_flag = False
            modem_exception_flag = True

    if return_mail is True:
        subject = "Status Report: {}".format(datetime.datetime.today())
        message = ("-" * 30) + "\n" + title_str + "\n" + ("-" * 30) + "\n" + services_str

        send_mail(subject=subject, message=message, receiver_email=value.admin_email)
        return

    if break_flag is True:
        message_print("Status Break!")
        subject = title_str + " Break!"
        message = services_str
        send_mail(subject=subject, message=message, receiver_email=value.admin_email)
        return

    if value.mail_exception_flag is True:
        message_print(title_str="Attempting to restart email service")
        time.sleep(value.interval)
        mail_setup()

    for user in User._registry:
        if user.modem_flag is False:
            time.sleep(value.interval)
            message_print(title_str=("Attempting to restart {}'s modem".format(user.name)))
            user.thread = threading.Thread(target=connect_modem, args=(user,))
            user.thread.start()

    message_print(title_str, (services_str, ""))

    if value.mail_exception_flag is True or modem_exception_flag is True:
        time.sleep(value.interval)
        message_print(title_str="Checking status again")
        status(break_flag=True)
        return


def main():
    # Read user data from userdata.txt
    read_userdata()

    # Uses user data to identify which serial port has been assigned to which phone number/ user
    read_portdata()

    # Creates a list of threads, one for each user in the User class registry.
    # Each thread handles the connection the user's modem.
    thread_lst = [threading.Thread(target=connect_modem, args=(user,)) for user in User._registry]
    status_thr = threading.Thread(target=status_thread)

    for i in range(len(thread_lst)):
        User._registry[i].thread = thread_lst[i]

    try:
        # Starts the connect_modem threads from thread_lst
        for i in thread_lst:
            message_print("Starting {}".format(i))
            i.start()
        # Starts the mail read service, it periodically checks for incoming emails
        message_print("Setting up mail")
        mail_setup()

        status_thr.start()
        status(return_mail=True)
    finally:
        pass
        for i in thread_lst:
            i.join()



# fetches configuration data from conf.txt. This has to happen before main
working_dir, slash_var = read_conf()
value = GlobalVal(working_dir, slash_var)


if __name__ == '__main__':
    main()

# logging received emails, sent emails, received sms, sent sms
# error handling
# Editable mail formatting
# bare except
