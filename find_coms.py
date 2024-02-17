import os
import subprocess
import datetime
import time

headers = ""
line = ""
com_lst = []


def fetch_coms_lin():
    # This function works by listing and sorting through the items in /sys/class/tty.
    tty_acm_lst = []

    result = subprocess.run(["ls", "/sys/class/tty"], stdout=subprocess.PIPE)

    # Turns the stdout string into a list
    tty_lst = str(result.stdout).split("\\n")

    # Finds all the serial "ttyACM" ports in 'tty_lst' and appends them to 'tty_acm_lst'
    for i in tty_lst:
        if "ttyACM" in i:
            tty_acm_lst.append(i)

    # Reformats items in 'tty_acm_lst' to be accepted by the modem
    for i in tty_acm_lst:
        com_lst.append("/dev/{}".format(i))
    return com_lst


def fetch_coms_win():

    # This function hinges on the windows cmd "wmic path WIn32_SerialPort".
    # The output of wmic is extremely verbose.

    index_marker = 0
    # Uses subprocess to fetch com data from wmic
    s = 'wmic path Win32_SerialPort'
    d = subprocess.Popen(s, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()[0]

    # Turns the stdout string into a list
    x = d.split()

    # Finds every item that contains "COM", and adds it to 'com_lst' if it is unique + some formatting
    for i in x:
        temp = str(i).strip("b\'").replace('(', '').replace(')', '')
        if "COM" in temp:
            if temp not in com_lst:
                com_lst.append(temp)

    # Removes "COM1", I have no idea why but trying to connect to "COM1" causes the program to hang/softlock
    for i in com_lst:
        if i == "COM1":
            com_lst.remove(i)
    return com_lst
