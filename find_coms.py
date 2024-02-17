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


def find_top(lst):
    top = 0
    index_var = []
    for i in lst:
        if int(i[2]) > int(top):
            top = i[2]
            index_var = i
    return index_var



x = "Orleans wine 697\nGiessen wine 714\nAmsterdam wine 718\n*Groningen wine 928" \
    "\n*Warszawa wine 1024\nTorun Wine 846\nGrodno Wine 836\nMinsk wine 756\nOstrog wine 892" \
    "\nKherson wine 878\nKiev wine 756\n*Pskov wine 968\nMinsk wine 812\nLublin wine 756" \
    "\nGiessen wine 760\nMilano wine 736\nNapoli wine 760\nMestre wine 912"
x_lst = x.split("\n")
split_lst = []
top_lst = []


for i in x_lst:
     split_lst.append(i.split(" "))

for i in range(len(split_lst)):
    y = find_top(split_lst)
    top_lst.append(y)
    split_lst.remove(y)

for i in top_lst:
    print(i)