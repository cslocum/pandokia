'''
pandokia.helpers.filecomp - a general interface for intelligently
    comparing two files

contents of this module:

    compare_files( list, okroot=None, tda=None )
            list is a list of (filename, comparison_type)
            okroot is the base name of the okfile.
            tda is a dict to update with the name of the okfile

            This function is probably what you want to use in your test.

    command(str, env) 
            portable way to run a shell command (the python library has
            many ways to do this, but nearly all are deprecated.  This
            interface is meant to use whichever one is in favor.)

    check_file( name, comparator, reference_file, header_message=None, 
        quiet=False, raise_exception=True, cleanup=False, ok_file_handle=None, 
        **kwargs )
            Compare a file to a reference file, using a specified comparator.
            It can display header_message before the comparison, raise an
            AssertionError if the files do not match, delete the input file
            after comparison (cleanup), and write a pdk compliant okfile.

    file_comparators[ ]
            a dict that converts comparator names to a function that performs
            the comparison.  This is here so you can add your own comparators.

    cmp_example( )
            an example of how to make your own comparison function; this is
            not actually used, but you can look at the docstring.

    ensure_dir( name )
            make sure directory exists, creating if necessary.  (There is no
            function like this in the python library.)

'''

__all__ = [ 'command', 'check_file', 'file_comparators', 'compare_files', 'ensure_dir' ]

import os
import re
import sys
import subprocess
import difflib


###
### "portable" way to run a shell command.  Use this in your
### tests to run a command
###

# The standard python library contains MANY methods for starting a
# child process, but nearly all of them are deprecated.  When subprocess
# becomes deprecated, we can update it once here instead of in every
# test that anybody writes.

# bug: capture stdout/stderr of child process and repeat it into
# sys.stdout/sys.stderr (so nose can capture it).
def command(s, env=None) :
    sys.stdout.flush()
    sys.stderr.flush()
    r = subprocess.call(s, shell=True, env=env)
    if r < 0 :
        raise Exception("signal %d from %s"%(-r, s) )
    return r

###
### Various file comparisons
###
### true = same
### false = different
###

def cmp_example( the_file, reference_file, header_message, quiet, **kwargs ) :
    '''
    cmp_example(  the_file, reference_file, header_message, quiet, **kwargs ) 

    This is an example of how to write your own file comparison function.
    See also the source code.

        the_file is the input file that we are testing.

        reference_file is the reference file that we already know to be correct.

        header_message is printed before the comparison.  Use this if you want
        to say something about what you are doing.  Notably, this is useful
        if your comparison might print things.

        quiet is true to suppress all output.  Not all comparison functions
        are capable of this, because some of them use external packages
        (e.g. fitsdiff) that are too chatty.

        kwargs is a place for optional args that may influence how the
        comparison takes place.  For example, you might use this to specify
        to ignore case, to compare numbers with a certain tolerance, or to
        ignore certain fields in the file.

    This function returns True if the files are the same (according to the
    comparison parameters given).  Return False otherwise.  Raise an exception
    if some exceptional condition prevents you performing the comparison.

    Define a function like this, then add it to the dictionary with a commmand
    like:
        pandokia.helpers.filecomp.file_comparators['example'] = cmp_example

    You can then use it by calling check_file:

        from pandokia.helpers.filecomp import check_file

        # simplest form
        check_file('output_file.txt', 'example')

        # more complex form - see check_file for detail
        check_file('output_file.txt', 'example', msg='Example Compare:',
            cleanup=True )

    '''
    # You can see I just copied cmp_binary for an example.
    if ( not quiet ) and ( header_message is not None ) :
        sys.stdout.write(header_message)
    r=command("cmp -s %s %s"%(the_file, reference_file))
    if r == 1:
        if not quiet :
            sys.stdout.write("file match error: %s\n"%the_file)
        return False
    elif r != 0:
        raise OSError("cmp command returned error status %d"%r)
    return True


###
### binary file compare
###

def cmp_binary( res, ref, msg, quiet, **kwargs ) :
    '''
    cmp_binary - a byte-for-byte binary comparison; the files must
        match exactly.  No kwargs are recognized.
    '''
    try :
        f1 = open(res, 'r')
    except :
        print "cannot open result file:",res
        raise

    try :
        f2 = open(ref,'r')
    except :
        f1.close()
        print "cannot open reference file",ref
        raise

    # pick the length out of the stat structure
    s1 = os.fstat(f1.fileno())[6]
    s2 = os.fstat(f2.fileno())[6]

    if s1 != s2 :
        print "files are different size:"
        print "    %s %d"%(res,s1)
        print "    %s %d"%(ref,s2)
        f1.close()
        f2.close()
        return False

    blksize=65536
    offset=0
    while 1 :
        d1 = f1.read(blksize)
        d2 = f2.read(blksize)

        if d1 == '' and d2 == '' :
            f1.close()
            f2.close()
            return True

        if d1 == d2 :
            continue

        # bug: be nice to show the offset where they are different
        print "files are different: ",res,ref
        f1.close()
        f2.close()
        return True

    # not reached

###
### FITS - Flexible Image Transport System
###

#
# This uses fitsdiff from STSCI_PYTHON, an astronomical data analysis package
#
# http://www.stsci.edu/resources/software_hardware/pyraf/stsci_python
#

def cmp_fits( the_file, reference_file, msg, quiet, **kwargs ) :
    '''
    cmp_fits - compare fits files.  kwargs are passed through to fitsdiff
    '''

    try :
        # new package name in stsci_python >= 2.12
        import stsci.tools.fitsdiff as fitsdiff
    except :
        import pytools.fitsdiff as fitsdiff

    sys.stdout.write("FITSDIFF %s %s\n"%(the_file, reference_file))
    if quiet:
        sys.stdout.write("(sorry - fitsdiff does not know how to be quiet)\n")

    d = fitsdiff.fitsdiff( the_file, reference_file, ** kwargs )

    # fitsdiff returns nodiff -- i.e. 0 is differences, 1 is no differences
    if d == 0 :
        return False
    else :
        return True

###
### text comparison
###

cmp_text_timestamp = None

def cmp_text_assemble_timestamp() :
    # This module assembles regular expressions for many of the common
    # date specification formats we find in our data files. It includes
    # the pieces from which such dates are constructed for easy expansion.
    # 
    # Created by RIJ, Jan 26 2006
    # Modified for use with the regtest software by VGL, Jun 1 2006
    # copied into pandokia.helpers May 2010

    # bug: This should really be 1) a list/dict/whatever that can be updated,
    # 2) dynamically generated as needed.  In fact, I just copied this out
    # of stsci_regtest and tweaked it a bit to use it here.

    #String specifications of the pieces
    Dow = '(Sun|Mon|Tue|Wed|Thu|Fri|Sat)'
    Mon ='(Jan|Feb|Mar|Apr|May|Jun' + \
              '|Jul|Aug|Sep|Oct|Nov|Dec)'
    #Numeric specifications of the pieces
    MN = '(0[1-9]|1[0-2])'
    DD = '([ 0][1-9]|[12][0-9]|3[01])'
    HH = '([01][0-9]|2[0-3])'
    MM = '([0-5][0-9])'
    SS = '([0-5][0-9])'
    TZ = '(HS|E[SD]T)'
    YYYY = '(19|20[0-9][0-9])'
    #Specification of separators
    sep = '( |:|-)'


    #Date specifications constructed from the pieces
    Date1 = Dow+sep+Mon+sep+DD+sep+HH+sep+MM+sep+SS+sep+TZ+sep+YYYY
    Date2 = Dow+sep+HH+sep+MM+sep+SS+sep+DD+sep+Mon+sep+YYYY
    Date3 = Mon+sep+DD+sep+HH+sep+MM
    Kdate = '^#K DATE       = '+YYYY+sep+MN+sep+DD
    Ktime = '^#K TIME       = '+HH+sep+MM+sep+SS

    #Any common datespec
    #(Sorry, Kdate/Ktime are not included because it overflows the
    #named-group limit of 100)

    global cmp_text_timestamp
    cmp_text_timestamp = "%s|%s|%s"%(Date1,Date2,Date3)


# This was copied out of the ASCII comparison in the old regtest code.
# It could probably make use of the standard python diff library 
# instead.

def cmp_text( the_file, reference_file, msg, quiet, **kwds ) :
    '''
    cmp_text - compare files as text

    kwargs are:
        ignore_wstart=xxx   ignore words that start with this pattern
        ignore_wend=xxx     ignore words that end with this pattern
        ignore_regexp=xxx   ignore this regular expression
        ignore_date=true    ignore various recognized date formats

    ignored patterns are replaced with ' IGNORE '
    '''

    diffs = [ ]
    ignore = [ ]
    ignore_raw = { }
    files_are_same = True

    for val in kwds.get('ignore_wstart',[]):
        if ignore_raw.has_key('wstart'):
            ignore_raw['wstart'].append(val)
        else:
            ignore_raw['wstart']=[val]
        pattern=r'\s%s\S*\s'%val
        ignore.append(pattern)

    for val in kwds.get('ignore_wend',[]):
        if ignore_raw.has_key('wend'):
            ignore_raw['wend'].append(val)
        else:
            ignore_raw['wend']=[val]
        pattern=r'\s\S*%s\s'%val
        ignore.append(pattern)

    for val in kwds.get('ignore_regexp',[]):
        ignore_raw['regexp']=val
        ignore.append(val)

    if kwds.get('ignore_date',False):
        ignore_raw['date']=True
        if cmp_text_timestamp is None :
            cmp_text_assemble_timestamp()
        ignore.append(cmp_text_timestamp)

    #Compile them all into a regular expression
    if len(ignore) != 0:
        ignorep=re.compile('|'.join(ignore))
    else:
        ignorep = None

    th=open(the_file)
    rh=open(reference_file)

    test=th.readlines()
    ref=rh.readlines()

    th.close()
    rh.close()

    if len(test) != len(ref):
        #Files of different sizes cannot be identical
        diffs=[('%d lines'%len(test),'%d lines'%len(ref))]
        files_are_same = False

    else:
        for i in range(len(ref)):
            #This may be slow, but it's clean
            if ignorep is not None:
                tline=ignorep.sub(' IGNORE ', test[i])
                rline=ignorep.sub(' IGNORE ', ref[i])
            else:
                tline=test[i]
                rline=ref[i]
            if tline != rline:
                files_are_same = False
                diffs.append((tline,rline))

    if files_are_same :
        return True

    # If we get this far, the files are different.  If quiet, it is
    # sufficient to know that they are different, so we return.
    if quiet :
        return False

    # Otherwise, we speak in detail about the comparison.
    if msg is not None :
        sys.stdout.write("%s\n",msg)

    fh=sys.stdout

    fh.write("\n")
    fh.write("Text Comparison\n")
    fh.write("Test file:      %s\n"%the_file)
    fh.write("Reference file: %s\n"%reference_file)
    fh.write("\n")
    if len(ignore_raw) > 0:
        fh.write("Patterns to ignore: \n")
        for k in ignore_raw:
            fh.write('  %s: %s\n'%(k,ignore_raw[k]))
    fh.write('\n')
    fh.flush()

    fwidth = max(len(the_file),len(reference_file))
    
    for tline,rline in diffs:
        fh.write("%-*s: %s\n"%(fwidth,the_file,tline.rstrip()))
        fh.write("%-*s: %s\n"%(fwidth,reference_file,rline.rstrip()))
        fh.write("\n")
    fh.flush()

    return False

###
### 
###

def cmp_diff( fromfile, tofile, msg, quiet, **kwds ) :

    if '-C' in kwds :
        n = kwds['-C']
    else :
        n = 3

    # The rest is basically "A command-line interface to difflib" from
    # the python docs for difflib.
    fromdate = time.ctime(os.stat(fromfile).st_mtime)
    todate = time.ctime(os.stat(tofile).st_mtime)
    fromlines = open(fromfile, 'U').readlines()
    tolines = open(tofile, 'U').readlines()

    diff = difflib.unified_diff(fromlines, tolines, fromfile, tofile,
                                    fromdate, todate, n=n)

    diff = list(diff)
    if len(diff) :
        if not quiet :
            if msg :
                sys.stdout.write(msg)
            sys.stdout.writelines(diff)
            sys.stdout.write('========\n')
        return False
    else :
        return True
    


###
### end of format-specific file comparison functions
###


###
### Here are the built-in comparisons available; add your own if necessary
###

file_comparators = {
    'binary':       cmp_binary,
    'fits':         cmp_fits,
    'text':         cmp_text,
    'diff':         cmp_diff,
}

###
###
###

def update_okfile(okfh, name, ref):
    
    okfh.write("%s %s\n"%(os.path.abspath(name),
                          os.path.abspath(ref)))

###
### compare a single file
###
    
def check_file( name, cmp, ref=None, msg=None, quiet=False, exc=True,
                cleanup=False, okfh=None, **kwargs ) :
    """
    status = check_file( name, cmp, msg=None, quiet=False, exc=True,
                         cleanup=False, okfh=None, **kwargs )

    name = file to compare

    cmp = comparator to use

    ref = file to compare against. If None, it lives in a ref/ dir
           under the dir containing the file to compare

    exc=True: raise AssertionError if comparison fails

    cleanup=True: delete file "name" if comparison passes

    okfh is a file-like object to write the okfile information; it must
        have a write() method.  If None, no okfile is written.

    msg, quiet, **kwargs: passed to individual comparators

    Returns: 
       True if same
       False if different (but raises exception if exc=True)

    """
    #Make sure we have a comparator
    if not cmp in file_comparators :
        raise ValueError("file comparator %s not known"%str(cmp))

    #Construct the reference file if necessary
    if ref is None:
        ref = os.path.join(os.path.dirname(name),
                           'ref',
                           os.path.basename(name))
    #Do the comparison
    try:
        r = file_comparators[cmp](name, ref, msg, quiet, **kwargs )
    #Catch exceptions so we can update the okfile
    except Exception:
        if okfh:
            update_okfile(okfh, name, ref)
        raise

    #Clean up file that passed if we've been asked to
    if r :
        if cleanup:
            try:
                os.unlink(name)
            except Exception:
                pass

    #Update the okfile if the test failed
    else:
        if okfh:
            update_okfile(okfh, name, ref)

        #Last of all, raise the AssertionError that defines a failed test
        if exc :
            raise(AssertionError("files are different: %s, %s\n"%(name,ref)))
    #and return the True/False (Pass/Fail) status
    return r


###
### a file comparator that does everything you need to check several
### output files in a single test.  (but not yet with all the options of
### compare_file)
###

def compare_files( list, okroot=None, tda=None ):
    '''
    compare_files( list, okroot=None, tda=None )

        list is a tuple of (filename, comparator, kwargs) 
            filename is the name of a file in the directory out/; it is
                compared to a file of the same name in the directory ref/,

            comparator is the name of the comparator to use.  The default
                system has 'text', 'binary', and 'fits'.

            kwargs is a dict of keyword args to pass to comparator
                function, or None.  You may omit kwargs if it is not needed.

        okroot is the bas name of the okfile.  If present, an okfile named
            okroot+'.okfile' is created.  Normally, you would use the
            basename of the current file plus the test name.

        tda is the tda dict.  If there is a tda dict and an okfile, the
            "_okfile" tda is set.

    In your code, you would write something like:

        x = compare_files(
                list = [
                    ( 'binary_output',  'binary' ),
                    ( 'text_output',    'binary', { 'ignore_date' : True } ),
                    ],
                okroot= __file__ + '.testname',
                tda=tda
                )

        if x :
            raise x

    '''

    # see if we are using an okfile; if we are, get it ready
    if okroot is not None :
        okfn = os.path.join(os.getcwd(), okroot + '.okfile')
        if tda is not None :
            tda['_okfile'] = okfn
        try :
            os.unlink(okfn)
        except :
            pass
        okfh = open(okfn, 'w')
    else :
        okfh = None

    # ret_exc is the exception that the application should raise
    # to fail/error the test.  We want to compare all the files in
    # the list, then pick one of the worst-case exceptions to return.
    # We do this by looping over all the files and only remembering an
    # exception that is worse than what we have seen so far.
    ret_exc = None

    for x in list :
        # pick out file name, comparator type, kwargs (optional)
        if len(x) > 2 :
            name, type, kwargs = x
        else :
            name, type = x
            kwargs = { }
    
        # perform the comparison
        try :
            print "\nCOMPARE:",name
            check_file( name='out/'+name, cmp=type, ref='ref/'+ name, okfh=okfh, exc=True)

        # assertion error means the test fails
        except AssertionError, e :
            print "FAIL"
            if ret_exc is None :
                ret_exc = e

        # any other exception means the test errors
        except Exception, e:
            print "ERROR",str(e)
            if ( ret_exc is None ) or ( isinstance(e, AssertionError) ) :
                ret_exc = e

    print ""

    # remember to close the okfile
    okfh.close()

    # return the exception
    return ret_exc

###
### what os.makedirs should have been...
###

def ensure_dir(name) :
    '''
    Create a directory hierarchy, ignoring any exceptions.  
    There is no native python function that does this.  

    If there is an error, presumably your code will try to use
    the directory later and detect the problem then.
    '''
    try :
        os.makedirs(name)
    except :
        pass


###
### checking age of files
###

import os
import time

def file_age(f) :
    st = os.stat( f )
    return time.time() - st.st_mtime

def file_age_ref( other=None, days=0, hours=0 ) :
    if other is None :
        ref = ( days * 86400 + hours * 3600 )
    else :
        ref = file_age(other)
    return ref

def t_to_s( sec ) :
    days = int(sec) / 86400
    sec = sec - days * 86400
    hours = int(sec) / 3600
    sec = sec - hours * 3600
    min = int(sec) / 60
    sec = sec - min * 60
    sec = sec - hours * 3600
    return '%d days %d:%02d:%02d'%(days,hours,min,sec)

def assert_file_older( f, other=None, days=0, hours=0 ) :
    f_age = file_age(f)
    ref_age = file_age_ref( other, days, hours )
    print "XX",f_age, ref_age
    if f_age < ref_age :
        assert False, 'file %s is %s older'%(f,t_to_s(ref_age - f_age))

def assert_file_newer( f, other=None, days=0, hours=0 ) :
    f_age = file_age(f)
    ref_age = file_age_ref( other, days, hours )
    if f_age > ref_age :
        assert False, 'file %s is %s newer'%(f,t_to_s(f_age - ref_age))