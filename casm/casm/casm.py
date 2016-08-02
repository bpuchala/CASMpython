import os, json

def jobname(configdir):
    """Return a name for PBS jobs for configuration in 'configdir'
       Returns "SCEL_name.config_name".
    """
    tmp = os.path.split(os.path.abspath(configdir))
    return os.path.split(tmp[0])[1] + "." + tmp[1]

def project_path(dir=None):
    """
    Crawl up from dir to find '.casm'. If found returns the directory containing the '.casm' directory.
    If not found, return None.
    
    Args:
    If dir == None, set to os.getcwd()
    """
    if dir == None:
      dir = os.getcwd()
    if not os.path.isdir(dir):
      raise Exception("Error, no directory named: " + dir)
    curr = dir
    cont = True
    while cont == True:
        test_path = os.path.join(curr,".casm")
        if os.path.isdir(test_path):
            return curr
        elif curr == os.path.dirname(curr):
            return None
        else:
            curr = os.path.dirname(curr)
    return None

#def casm_settings_path():
#    """
#    Crawl up and find project_settings.json
#    """
#    configdir = os.getcwd()
#    curr = configdir
#    cont = True
#    while cont == True:
#        candidate=os.path.join(curr,".casm")
#        if os.path.exists(candidate):
#            return candidate
#        elif curr == os.path.dirname(curr):
#            return None
#        else:
#            curr = os.path.dirname(curr)
#

#Move this into DirectoryStructure





