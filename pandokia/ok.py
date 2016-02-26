#
# pandokia - a test reporting and execution system
# Copyright 2013, Association of Universities for Research in Astronomy (AURA) 
#

#
# pdk ok
#
# an okfile contains information to update a single test that uses
# reference files.  Each line of the file contains two fields separated
# by spaces.  The first field is the name of the output file, and the
# second field is the name of the reference file.  If the second field
# is missing, the reference file has the same name in the directory "ref/".

from optparse import OptionParser
import datetime, os, re, shutil, sys
import pandokia


# we expect to run "pdk ok -w hostname.ok" in some pandokia installations that
# don't have databases defined; this is ok, since this usage doesn't actually
# use a database for anything
try:
    pdk_db = pandokia.cfg.pdk_db
except AttributeError:
    pass


old = '.%s.old' %datetime.date.today().isoformat()

pdk_updates = '/eng/ssb/tests/pdk_updates/'
old_pdk_updates = os.path.join(pdk_updates, 'old')
if not os.path.exists(old_pdk_updates):
    try:
        os.makedirs(old_pdk_updates)
    except:
        print('couldn\'t make directory %s' %old_pdk_updates)



def run(args):
    parser = OptionParser('Usage: pdk ok [options]')

    parser.add_option(
        '-v', '--verbose', dest = 'verbose', action = 'store_true',
        default = False, help = 'print lots of crap'
    )
    parser.add_option(
        '-w', dest = 'process_webfile', default = False, action = 'store_true',
        help = 'process an old-style hostname.ok file generated by the Pandokia ' \
            'cgi; files to okify must be on localhost'
    )
    parser.add_option(
        '-k', '--okfile', dest = 'okfile', default = False, action = 'store_true',
        help = 'process a single okfile; the okfile must be on localhost'
    )
    parser.add_option(
        '--host', dest = 'filter_by_host', default = None,
        help = 'filter by hostname'
    )
    parser.add_option(
        '--project', dest = 'filter_by_project', default = None,
        help = 'filter by project'
    )
    parser.add_option(
        '--context', dest = 'filter_by_context', default = None,
        help = 'filter by context'
    )
    parser.add_option(
        '--commit', dest = 'commit', default = False, action = 'store_true',
        help = 'commit okified reference file(s) to svn'
    )
    parser.add_option(
        '--commit-git', dest = 'commit_git', default = False, action = 'store_true',
        help = 'commit and push okified reference file(s) to git'
    )

    opt, args = parser.parse_args(args)

    # validate user input
    if opt.process_webfile and len(args) < 1:
        print('ERROR: missing argument (hostname.ok)')
        sys.exit(1)

    fn = None
    if len(args) > 1:
        print('ERROR: too many arguments')
        sys.exit(1)
    elif len(args) == 1:
        fn = args[0]

    # do whatever...
    if opt.process_webfile:
        return process_webfile(opt, fn)
    elif opt.okfile:
        return process_okfile(opt, fn)
    else:
        return process_database(opt)



def process_webfile(opt, fn):
    web_re = re.compile('^[A-Za-z0-9/_.-]*$')

    file = open(fn)
    lines = [ln.strip() for ln in file.readlines()]
    lines = [ln for ln in lines if not ln.startswith('#')]
    lines = [ln for ln in lines if len(ln) > 0]
    file.close()

    transactions = []
    in_trans = False
    T = {}
    err = 0
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 4 and parts[0] == 'TRANS':
            if in_trans:
                transactions.append(T)
                T = {}
            parts.pop(0)
            T['ip'] = parts.pop(0)
            T['user'] = parts.pop(0)
            T['qid'] = parts.pop(0)
            T['comment'] = ''
            try:
                T['comment'] = ' '.join(parts)
            except:
                pass
            T['okfiles'] = []
            in_trans = True
        
        elif len(parts) == 1:
            okfile = ln
            if not web_re.match(okfile):
                print('invalid okfile %s %s %s' %(T['ip'], T['user'], okfile))
                err += 1
                continue
            else:
                T['okfiles'].append(ln)
        else:
            print('invalid input in web file: %s' %ln)
            err += 1
    transactions.append(T)


    ref_repo = False
    if 'PDK_REFS' in list(os.environ.keys()):
        PDK_REFS = os.environ['PDK_REFS']
        ref_repo = True
        if opt.commit:
            # we want to commit anything that's modified in the reference file
            # repository before we process the transactions, in case there are
            # any uncommitted changes
            cmd = 'svn commit %s -m "committing uncommitted references"' %PDK_REFS
            print()
            print(cmd)
            ret = os.system(cmd)
            if not ret == 0:
                err += 1


    for t in transactions:
        sys.stdout.flush()
        sys.stderr.flush()

        refs_to_commit = []
        for okfile in t['okfiles']:
            ret, refs = process_okfile(opt, okfile, return_refs = True)
            err += ret
            if refs:
                for r in refs:
                    refs_to_commit.append(r)

        sys.stdout.flush()
        sys.stderr.flush()

        # do svn commit
        if len(refs_to_commit) > 0 and opt.commit:
            ref_str = ' '.join(refs_to_commit)

            # add reference files, in case they are new
            for r in refs_to_commit:
                cmd = 'svn add -q %s --parents' %r
                print(cmd)
                ret = os.system(cmd)
                if not ret == 0:
                    err += 1

            sys.stdout.flush()
            sys.stderr.flush()

            # commit reference files
            if ref_repo:
                cmd = 'svn commit %s -m "(%s, QID=%s) %s"' %(
                    PDK_REFS,
                    t['user'],
                    t['qid'],
                    t['comment']
                )
            else:
                cmd = 'svn commit %s -m "(%s, QID=%s) %s"' %(
                    ref_str,
                    t['user'],
                    t['qid'],
                    t['comment']
                )
            print()
            print(cmd)
            ret = os.system(cmd)
            if not ret == 0:
                err += 1

        # do git commit and push
        if len(refs_to_commit) > 0 and opt.commit_git:
            ref_str = ' '.join(refs_to_commit)

            # commit reference files
            if ref_repo:
                os.chdir(PDK_REFS)
                cmd = 'git commit -a -m "(%s, QID=%s) %s"' %(
                    t['user'],
                    t['qid'],
                    t['comment']
                )
                print()
                print(cmd)
                ret = os.system(cmd)
                if not ret == 0:
                    err += 1

    try:
        os.rename(fn, fn + old)
        os.system('mv %s %s' %(fn + old, old_pdk_updates))
    except Exception as e:
        print('failed to backup %s' %fn)
        print(e)
        err += 1

    return err



''' process all new okify transactions in the database and generate
    hostname.ok files
'''
def process_database(opt):

    # find all transactions in ok_transactions where status = new
    c = pdk_db.execute("SELECT trans_id, username, user_comment, ip_address, status, qid FROM ok_transactions WHERE status='new'")
    for trans_id, username, user_comment, ip_address, status, qid in c:

        trans = dict(
            qid = qid,
            user = username,
            ip = ip_address,
            comment = user_comment,
            hosts = {}
        )

        # get ok items for this transaction
        cc = pdk_db.execute("SELECT key_id, status FROM ok_items WHERE trans_id = :1", [trans_id])
        for key_id, status in cc:
            ok_status = status
            if ok_status == 'new':
                
                # get ok item details
                ccc = pdk_db.execute("SELECT project, context, test_name, host FROM result_scalar WHERE key_id = :1", [key_id])
                project, context, test_name, host = ccc.fetchall()[0]

                # get item's okfile
                ccc = pdk_db.execute("SELECT value FROM result_tda WHERE key_id = :1 and name = '_okfile'", [key_id])
                okfile = ccc.fetchall()[0][0]

                # make sure this ok item meets user-specified criteria
                do_ok = True
                if opt.filter_by_project:
                    if not opt.filter_by_project == project:
                        do_ok = False
                if do_ok and opt.filter_by_context:
                    if not opt.filter_by_context == context:
                        do_ok = False
                if do_ok and opt.filter_by_host:
                    if not opt.filter_by_host == host:
                        do_ok = False

                if do_ok:
                    if host not in list(trans['hosts'].keys()):
                        trans['hosts'][host] = []
                    trans['hosts'][host].append(okfile)

                    # update database entry for this ok item; set status = "done"
                    ccc = pdk_db.execute("UPDATE ok_items SET status = 'done' WHERE key_id = :1", [key_id])
                    pdk_db.commit()

        # for each host in trans['hosts'].keys(), update host.ok (create if
        # doesn't exist)
        for host, okfiles in list(trans['hosts'].items()):
            fn = os.path.join(pdk_updates, '%s.ok' %host)
            if not os.path.exists(fn):
                os.system('touch %s' %fn)

            lines = ['\nTRANS %s %s %s %s' %(trans['ip'], trans['user'], trans['qid'], trans['comment'])]
            for okfile in okfiles:
                lines.append(okfile)

            file = open(fn, 'a')
            file.write('\n'.join(lines))
            file.close()
            print('generated %s' %fn)

    # loop over ok_transactions again and see if all associated ok_items have
    # been done; if so, mark transaction status = done
    c = pdk_db.execute("SELECT trans_id, status FROM ok_transactions WHERE status='new'")
    for trans_id, status in c:
        done = True
        cc = pdk_db.execute("SELECT key_id, status FROM ok_items WHERE trans_id = :1", [trans_id])
        for key_id, status in cc:
            if status == 'new':
                done = False
                break
        if done:
            cc = pdk_db.execute("UPDATE ok_transactions SET status = 'done' WHERE trans_id = :1", [trans_id])
            pdk_db.commit()
            


def process_okfile(opt, fn, return_refs = False):
    try:
        file = open(fn)
    except Exception as e:
        print('\tcannot open %s' %fn)
        print('\t%s'% e)
        return 1, None

    print('\tokfile: %s' %fn)

    dirname = os.path.dirname(fn)

    err = 0
    refs = []
    for line in file:
        line = line.strip()
        if line.startswith('#'):
            continue
        line = line.split()
        if not len(line) == 2:
            print('\tinvalid input in okfile %s: %s' %(fn, line))
            err += 1
            continue

        src = line[0]
        dest = line[1]

        # watch carefully: os.path.join can tell whether src is a fully qualfied
        # path, and if it is, it ignores dirname, otherwise it uses src as a
        # relative path
        src = os.path.join(dirname, src)
        dst = os.path.join(dirname, dest)
        err += doit(src, dst, opt.verbose)
        if not err:
            refs.append(dst)

    file.close()

    try:
        os.unlink(fn)
    except IOError as e:
        print('\tcannot remove %s' %fn)
        print('\t%s'% e)
        err += 1

    if return_refs:
        return err, refs
    else:
        return err



# actually do the rename/copy with any directory create needed
def doit(src, dest, verbose) :

    # We ignore a lot of errors here with overly broad except clauses.
    # That is because the possible exceptions are not clearly defined,
    # and when you get one, you have to work to know what it means.
    # (e.g. you get IOError for both 'file not found' and 'disk is on fire')
    #
    # This function tries a lot of different things, and returns when it
    # thinks it has success.  If not, the last error it encounters will
    # still represent the real problem that the user needs to know about.

    if not os.path.exists(src):
        print("source (output from test) does not exist: %s"%src)
        return 1

    # Make sure the "old" reference file is not there.  If you do multiple
    # updates per day, you will lose some of the old reference files.
    try :
        os.unlink(dest+old)
    except :
        pass

    # rename the reference file to the "old" name
    try :
        os.rename(dest, dest+old)

    except Exception as e:
        if os.path.exists(dest) :
            print("cannot rename %s to %s"%(dest, dest+old))
            print(e)
            return 1

    # The destination file must not be there.
    try :
        os.unlink(dest)
    except :
        pass

    # try to rename the file; if it works, we're done
    try :
        os.rename(src,dest)
        return 0
    except :
        pass

    # maybe the destination directory is not there - ignore the exception
    # when the last directory is already there
    try :
        os.makedirs(os.path.dirname(dest))
    except :
        pass

    # maybe we created the directory and the rename can work now
    try :
        os.rename(src,dest)
        return 0
    except :
        pass

    # ok, maybe not, but maybe we can copy the file
    try :
        shutil.copyfile(src, dest)
    except IOError as e :
        # ok, we are now out of options - it didn't work
        print("cannot copy %s to %s"%(src,dest))
        print(e)

    return 1

