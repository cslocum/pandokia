"""This is the new means to email test reports to contacts.  As it takes shape 
users will be able to select which reports they like and the level of verbosity 
associated with said reports.
"""
TEST = True
import pandokia.common
import pandokia.contact_notify
import text_table
from collections import defaultdict

db = pandokia.common.open_db()

#A dictionary of test runs for easy storage.
test_runs = {}
test_summary = {}


#Let us insert some test data into the user_prefs table.
if False:
    query = 'INSERT INTO user_prefs VALUES (?,?)'
    for i in range(0,100):
        db.execute(query,('name_'+str(i),'email_'+str(i)))
    db.commit()
        
# insert pref if it exists
# format takes 'n', 's', 'f', or 'int'
def add_user_pref(username,project,format,maxlines=0):
    query = 'INSERT INTO user_email_pref VALUES (?,?,?,?)'
    check_query = "SELECT username FROM user_email_pref WHERE username=? AND project = ? AND format = ? AND maxlines = ?"
    has_entry = db.execute(check_query,(username,project,format,maxlines))
    if has_entry.fetchone():
        return 'has entry'
    else:
        db.execute(query,(username,project,format,maxlines))
        db.commit()
        return "Pref commited"

#Grabs the test runs that users are associated with.
def get_user_projects(username):
    query = """SELECT project, format, maxlines FROM user_email_pref WHERE username=? AND format <> 'N' ORDER BY project"""
    res = db.execute(query,(username,))
    res = [ (project, format, maxlines) for project, format, maxlines in res ]
    return res

#Let us get feed back on this
def project_test_run(test_run, project):
    hosts_q = """SELECT DISTINCT(host) FROM result_scalar WHERE test_run = ? AND project = ? 
             ORDER BY host, context, test_name"""
    context_q = """SELECT DISTINCT(context) FROM result_scalar WHERE test_run = ? AND project = ? 
            AND status <> 'P' ORDER BY host, context, test_name"""
    
    host_res = db.execute(hosts_q,(test_run,project))
    hosts = len([host for host, in host_res])
    
    context_res = db.execute(context_q,(test_run,project))
    contexts = len([context[0] for context in context_res])
    
    tests = {}
    res_ary = {}
    if (test_run,project) in test_runs :
        return test_runs[(test_run,project)]

    query = """SELECT host, test_name, context, status FROM result_scalar WHERE test_run = ? AND project = ? 
            AND status <> 'P' ORDER BY host, context, test_name """
    res = db.execute(query,(test_run,project))
    #res_ary = [ (host, test_name, context, status) for host, test_name, context, status in res]

    for host, test_name, context, status in res:
        tests[test_name] = tests.get(test_name,{'h' : [], 'c' : [], 's' : []})
        tests[test_name]['h'].append(host)
        tests[test_name]['c'].append(context)
        tests[test_name]['s'].append(status)

    #tests[test_name].sort()
    for test_name, test in tests.iteritems():
        if len(test['h']) < hosts or len(set(test['c'])) < contexts:
            for i in range(0,len(test['h'])):
                #print test['h'][i], hosts
                res_ary[test['h'][i]] =  res_ary.get(test['h'][i],[])
                res_ary[test['h'][i]].append((test['c'][i],test_name,test['s'][i]))
        elif len(test['h']) == hosts and len(set(test['c'])) == contexts:
            res_ary['All'] =  res_ary.get('All',[])
            res_ary['All'].append((test['c'][0],test_name,test['s'][0]))
    #Build up array of tuples 
    test_runs[(test_run,project)] = res_ary
    return res_ary

    
#summarize test with counts of pass fail error disabled and missing
# access dictionary with test_summary[(test_run,project)][host][status] host can be specific or all
def get_test_summary(test_run,project):
    sum_dict = {}
    all_hosts = {}
    if (test_run, project) in test_summary:
        return test_summary[(test_run,project)]
    query = """SELECT status,context, host FROM result_scalar WHERE test_run = ? AND project = ? """
    res = db.execute(query,(test_run,project))
    
    for status, context, host in res:
        sum_dict[host] = sum_dict.get(host,{})
        sum_dict[host][context] = sum_dict[host].get(context,{})
        sum_dict[host][context][status] = sum_dict[host][context].get(status,0) + 1

    for host in sum_dict.keys():
        for context in sum_dict[host].keys():
            for status in sum_dict[host][context].keys():
                all_hosts[status] = all_hosts.get(status,0) + sum_dict[host][context][status]
    sum_dict['All'] = all_hosts
    
    for host in sum_dict.keys():
        if host == 'All':
            sum_dict[host]['T'] = sum(sum_dict[host].values())
        else:
            for context in sum_dict[host].keys():
                sum_dict[host][context]['T'] = sum(sum_dict[host][context].values())    
    test_summary[(test_run,project)] = sum_dict
    #print sum_dict
    return sum_dict

# turn the summary into table content
def create_summary(test_run,project):
    sum_str = "Project summary for " + project + " and test_run " + test_run + "\n\n"
    cols = ['Host','Context','Total', 'Pass', 'Fail', 'Error', 'Disabled', 'Missing']
    stat_keys_sorted = ['T','P','F','E','D','M']
    sum_table = text_table.text_table()
    for col_name in cols:
        sum_table.define_column(col_name)
    test_summary = get_test_summary(test_run, project)
    hosts = test_summary.keys()
    hosts.sort()
    #for i, host in enumerate(hosts):
    #if host == 'All':
    sum_table.set_value(0, 0, 'All')
    sum_table.set_value(0, 1, 'All')
    for i, status in enumerate(stat_keys_sorted):
        sum_table.set_value(0,i+2, test_summary['All'].get(status,0))
    for i, host in enumerate(hosts):
        if host != 'All':
            contexts = test_summary[host].keys()
            contexts.sort()
            sum_table.set_value(i,0,host)
            for j, context in enumerate(contexts):
                sum_table.set_value(i+j,1,context)
                for k, status in enumerate(stat_keys_sorted):
                    sum_table.set_value(i+j,2+k,test_summary[host][context].get(status,0))
                
    #contexts  = test_summary[host].keys()
    #for context in context.sort():
    #print context
    #make up tables for this email.

    return sum_table
    
#create user emails based on format in user_email_pref
#THIS IS UGLY
def create_email(username, test_run) :
    user_email_q = """SELECT email FROM user_prefs WHERE username = ?"""
    user_email_res = db.execute(user_email_q,(username,))
    user_email = [email for email, in user_email_res]
    email = "Test report for %s:\n\n" % test_run
    projects = get_user_projects(username)
    num_proj = len(projects)
    send_notice = False

    for project in projects:
        project, format, maxlines = project

        # no need to compute anything if the user does not want to look at it
        if format == 'n' :
            continue

        # Do not print the project header yet.  format 'c' does not say anything at all
        # if there is nothing to report.

        if format == 'c' :
            # show only the test that the user is listed as a contact for.
            # (this needs work; see get_contact_report() for details)
            #
            r = pandokia.contact_notify.get_contact_report(username, project, test_run)
            if r is not None :
                email += "Project: "+ project + "\n\n"
                email += pandokia.contact_notify.get_contact_report(username, project, test_run)
                email += '\n'
                send_notice = True
            continue

        # The remaining options always show something, so we always need the project section header.
        email += "Project: "+ project + "\n\n"

        if format.capitalize() == 'F':
            all_hosts, some_hosts = build_report_table(test_run,project,maxlines)
            if all_hosts is not None :
                email += "These tests failed on all hosts and on all contexts\n"
                email += all_hosts.get_rst()
                email += "\n"
                send_notice = True
            if some_hosts is not None :
                email += "These tests failed on some hosts\n"
                email += some_hosts.get_rst()
                email += "\n"
                send_notice = True
            if all_hosts is None and some_hosts is None :
                email += "No anomalies to report\n\n"
            continue

        if format.capitalize() == 'S':
            summary = create_summary(test_run,project)
            email += summary.get_rst()
            email += '\n'
            send_notice = True
            continue

    if not send_notice :
        return None
    return email

def build_report_table(test_run,project,maxlines):
    all_hosts = text_table.text_table()
    some_hosts = text_table.text_table()
    cols = ['Host', 'Test Name', 'Context', 'Status']
    test_run = project_test_run(test_run,project);
    for col_name in cols:
        all_hosts.define_column(col_name)
        some_hosts.define_column(col_name)
    if len(test_run.keys()) == 0:
        return ( None, None )
    # This isn't quite right.
    # There are two different tables, so we need to be tracking
    # two different row numbers.
    row_a = 0
    row_s = 0
    trip = 0
    hosts = test_run.keys()
    hosts.sort()
    any_all_hosts = False
    any_some_hosts = False

    for i, host in enumerate(hosts):
        test_run[host].sort()
        if host == 'All':
            table = all_hosts
            row = row_a
        else:
            table = some_hosts
            row = row_s
        for j, val in enumerate(test_run[host]):
            if row >= maxlines and maxlines > 0:
                table.set_value(row,0,'The remainder of the output is suppressed')
                break
            if host == 'All' :
                any_all_hosts = True
            else :
                any_some_hosts = True
            table.set_value(row,0,host)
            test_name, context, status = val
            table.set_value(row,1,test_name)
            table.set_value(row,2,context)
            table.set_value(row,3,status)
            row = row + 1
        if host != 'All':
            # only need to save row_s because there is only one instance
            # of "All" n the list.
            row_s = row

    if not any_all_hosts :
        all_hosts = None
    if not any_some_hosts :
        some_hosts = None

    return (all_hosts, some_hosts)
        
#actually send the email
def sendmail(addy, subject, fname):
    """Interface to the mail system is sequestered here. Presently just
    uses the shell mail command."""
    if TEST:
        #then don't irritate people by sending test emails; send them
        #all to the user running the test instead
        args=(fname, subject+addy, getpass.getuser())
    else:
        args=(fname, subject, addy)
    mail_cmd = "cat %s | mail -s '%s' %s"%args
    stat=subprocess.call(mail_cmd, shell=True)
    return stat


def run(args):
    user = 'nobody'
    test_run = pandokia.common.find_test_run("daily_latest")
    if args:
        # for each user name, look it up the email address in the table
        users = [ ]
        for user in args :
            found = 0
            c = db.execute("SELECT email FROM user_prefs WHERE username = ?", (user,))
            for email, in c :
                users.append( (user, email) )
                found=1
            if not found :
                print "No email address known for user",user
    else:
        # get a list of all the (user, email) from the user prefs
        query = """SELECT username, email FROM user_prefs"""
        user_res = db.execute(query)
        users = [(user,email) for user,email in user_res]

    # compute the email to send to each user; send it.
    for user, email in users:
        msg = create_email(user, test_run)
        if msg is not None :
            print "=========="
            print "USER: ",user,"EMAIL:",email
            print "MSG:"
            print msg
        else :
            print "No email for ",user

#add_user_pref('user1','proj1','f','5')
#add_user_pref('user1','proj2','s','42')
#add_user_pref('user1','proj3','n')
#print test_runs['run2']
#print create_email('user1','run1')
