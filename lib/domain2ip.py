# !/usr/bin/env python
# -*- coding:utf-8 -*-
__author__ = 'bit4'
__github__ = 'https://github.com/bit4woo'

import dns.resolver
import dns.query
from netaddr import IPAddress,IPNetwork
import netaddr
import sys,os
import datetime
import Queue
import threading
import re
import urllib3
urllib3.disable_warnings()
from lib import myrequests
req = myrequests

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from lib.common import strip_list

def query(domain, record_type='A',server=None):
    domain = domain.strip()
    resolver = dns.resolver.Resolver()
    if server != None:
        resolver.nameservers = [server]
    ips = []
    try:
        resp = resolver.query(domain, record_type, raise_on_no_answer=False)
        if resp.response.answer:
            tmpip = []
            tmpcname = []
            for i in resp.response.answer:
                for j in i.items:
                    try:
                        #print "{0}   {1}".format(domain,j.address)
                        tmpip.append(j.address)
                    except:# CNAME here
                        #print "{0}   {1}".format(domain,j.to_text())
                        tmpcname.append(j.to_text())
            line ="{0}\t{1}\t{2}".format(domain.ljust(30),", ".join(tmpcname),", ".join(tmpip))
            if tmpip != None: #only collect IPs that don't use CDN （cname）
                ips.extend(tmpip)
            #print line
            return ips,line

        # If we don't receive an answer from our current resolver let's
        # assume we received information on nameservers we can use and
        # perform the same query with those nameservers
        if resp.response.additional and resp.response.authority:
            ns = [
                rdata.address
                for additionals in resp.response.additional
                for rdata in additionals.items
            ]
            resolver.nameservers = ns
            return query(resolver, domain, record_type)
        #print domain
        return [],domain
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout):
        #print domain
        return [],domain


def isIPAddress(str):
    try:
        IPAddress(str)
        return True
    except:
        return False


def domains2ips(domain_list):
    input_Queue = Queue.Queue()
    for item in domain_list:
        input_Queue.put(item)


    outout_ips_Queue = Queue.Queue()
    outout_lines_Queue = Queue.Queue()


    class customers(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)

        def run(self):
            while True:
                if input_Queue.empty():
                    break
                domain = input_Queue.get(1)
                #input_Queue.task_done() #no need in this program
                domain = domain.strip()
                try:
                    ips, line = query(domain, record_type='A')
                    print line
                    for ip in ips:
                        outout_ips_Queue.put(ip)
                    outout_lines_Queue.put(line)
                except Exception, e:
                    print e
                #
                # # signals to queue job is done
                # outout_ips_Queue.task_done()
                # outout_lines_Queue.task_done()

    for i in range(10):
        dt = customers()
        dt.setDaemon(True)
        dt.start()
        dt.join()#use this instead Queue.join()，Queue.join() will lead to thread always running!!

    # wait on the queue until everything has been processed
    # input_Queue.join()
    # outout_ips_Queue.join()
    # outout_lines_Queue.join()

    iplist =[]
    linelist = []
    while not outout_ips_Queue.empty():
        iplist.append(outout_ips_Queue.get(timeout=0.1))
    while not outout_lines_Queue.empty():
        linelist.append(outout_lines_Queue.get(timeout=0.1))
    return iplist,linelist

def targets2lines(target_list):
    input_Queue = Queue.Queue()
    for target in target_list:
        input_Queue.put(target)
    ips_Queue = Queue.Queue()
    lines_Queue = Queue.Queue()

    class customers(threading.Thread):
        def __init__(self):
            threading.Thread.__init__(self)

        def run(self):
            while True:
                if input_Queue.empty():
                    break
                target = input_Queue.get(1)
                # input_Queue.task_done() #no need in this program
                target = target.strip()
                http = "http://{0}".format(target)
                https = "https://{0}".format(target)
                lastURL1, code1, title1 = getTitle(http)
                lastURL2, code2, title2 = getTitle(https)

                titlelist = []
                if code1 != 503 and title1 != None:
                    titlelist.append(title1)
                if code2 != 503 and title2 != None and title2 != title1:
                    titlelist.append(title2)
                title = " || ".join(titlelist)

                if isIPAddress(target):
                    ips = [target]
                    if title == "":
                        line = ""
                    else:
                        line = "\t\t{0}\t{1}".format(target, title)
                        print line
                else:
                    ips, line = query(target)
                    if title == "":
                        line = ""
                    else:
                        line = "{0}\t{1}".format(line, title)
                        print line

                for ip in ips:
                    ips_Queue.put(ip)

                if line != "":
                    lines_Queue.put(line)

                # # signals to queue job is done
                # ips_Queue.task_done()
                # lines_Queue.task_done()

    for i in range(10):
        dt = customers()
        dt.setDaemon(True)
        dt.start()
        dt.join() #use this instead Queue.join()

    # input_Queue.join()
    # ips_Queue.join()
    # lines_Queue.join()

    iplist = []
    linelist = []
    while not ips_Queue.empty():
        iplist.append(ips_Queue.get())
    while not lines_Queue.empty():
        linelist.append(lines_Queue.get())

    return iplist,linelist


def getTitle(url):
    try:
        response= req.get(url)
        body = response.content
        code = response.status_code
        lastURL = response.url
        #reg_title = re.compile('<title>(.*?)</title>')#不能匹配换行，空格等字符
        reg_title = re.compile('<title>([\s\S]*?)</title>')
        title = reg_title.findall(body)

        if title.__len__() > 0:
            result_title = title[0].strip()
        else:
            result_title = "Title为空"
    except Exception, e:
        lastURL, code, result_title = None, None, None
    return lastURL, code, result_title

###########subnet / iplist convertion #########
def iprange(ip_str_list):
    ip_str_list = list(set(ip_str_list))
    ip_str_list= strip_list(ip_str_list)
    #直接获取各个C段
    subnet = set()
    for ip_str in ip_str_list:
        #print ip_str
        ip = IPNetwork(ip_str)
        ip.prefixlen =24
        subnet.add(ip.cidr)
    #print subnet

    #尝试根据IP缩小范围
    smaller_subnet =set()
    for net in subnet:
        tmpIPlist = []
        for ip_str in ip_str_list:
            ip = IPNetwork(ip_str)
            ip.prefixlen = 24
            if ip.cidr == net:#ip属于net
                tmpIPlist.append(ip_str)
        #print tmpIPlist
        if len(tmpIPlist) == 1:
            smaller_subnet.add(tmpIPlist[0])
        elif len(tmpIPlist) >=2:
            smaller = netaddr.spanning_cidr(tmpIPlist)  #type is IPNetwork
            #if smaller != net:
            smaller_subnet.add(smaller)
        elif len(tmpIPlist) ==0:
            print "{0} has no ip".format(net)

    result = []
    for item in smaller_subnet:
        result.append(str(item))
    return result

def smaller_network():
    #list = ['192.168.0.0', '192.168.0.245', '192.168.0.255']
    #list = ['192.168.2.245']
    x = netaddr.spanning_cidr(list)
    print x

def iprange2iplist(subnet_str_list):
    iplist =[]
    for subnet in subnet_str_list:
        if "/" in subnet:
            ips = IPNetwork(subnet)
            for x in ips:
                iplist.append(x.__str__())
                #print(x.__str__())
        else:
            ip = IPAddress(subnet)
            iplist.append(ip.__str__())
    return iplist




def main(domainfile,outputfile=None):
    if outputfile ==None:
        now = datetime.datetime.now()
        timestr = now.strftime("-%Y-%m-%d-%H-%M")
        outputfile = "domain2ip" + timestr + ".txt"
        outputfile= os.path.join(os.path.dirname(__file__), "..","output", outputfile)
    if  os.path.exists(domainfile):
        domains = open(domainfile,"r").readlines()
        x, lines = domains2ips(domains)
        lines.extend(x)
        open(outputfile,"w").writelines("\n".join(lines))
    else:
        print("file not found")

def test(switch,Domains):
    if switch:  # to get title
        ips, lines = targets2lines(Domains)
        iplist = set(iprange2iplist(iprange(ips))) - set(ips)
        ips1, lines1 = targets2lines(iplist)
        lines.extend(lines1)
    else:
        ips, lines = domains2ips(Domains)

    print ips
    print(lines)

if __name__ == "__main__":
    targetlist = open("D:\github\\all-seeing-eye\input\jd.com","r").readlines()
    #targets2lines(targetlist)
    domains2ips(targetlist)

