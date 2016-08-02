import os, math, sys, json, re, warnings
import pbs
import vasp
import casm
import casm.project
import vaspwrapper

class Relax(object):
    """The Relax class contains functions for setting up, executing, and parsing a VASP relaxation.

        The relaxation creates the following directory structure:
        config/
          calctype.name/
              run.0/
              run.1/
              ...
              run.final/

        'run.i' directories are only created when ready.
        'run.final' is a final constant volume run {"ISIF":2, "ISMEAR":-5, "NSW":0, "IBRION":-1}

        This automatically looks for VASP settings files in .../settings/calctype.name,
        where '...' is the nearest parent directory of 'self.configdir' in the CASM project repository

        Contains:
            self.configdir (.../config)
            self.calcdir   (.../config/calctype.name)

            self.settings = dictionary of settings for pbs and the relaxation, see vaspwrapper.read_settings

            self.auto = True if using pbs module's JobDB to manage pbs jobs
            self.sort = True if sorting atoms in POSCAR by type
    """
    def __init__(self, configdir=None, auto = True, sort = True):
        """
        Construct a VASP relaxation job object.

        Args:
            configdir: path to configuration
            auto: True if using pbs module's JobDB to manage pbs jobs

        """
        if configdir == None:
            configdir = os.getcwd()

        print "Working on directory "+str(configdir)

        print "Reading CASM settings"
        self.casm_settings = casm.project.ProjectSettings()
        if self.casm_settings == None:
            raise vaspwrapper.VaspWrapperError("Not in a CASM project. The file '.casm' directory was not found.")

        self.casm_directories=casm.project.DirectoryStructure()

        print "Constructing a CASM VASPWrapper Relax object"
        sys.stdout.flush()

        print "  Setting up directories"
        sys.stdout.flush()

        # store path to .../config, if not existing raise
        self.configdir = os.path.abspath(configdir)
        if not os.path.isdir(self.configdir):
            raise vasp.VaspError("Error in casm.vasp.relax: Did not find directory: " + self.configdir)
            sys.stdout.flush()

        # store path to .../config/calctype.name, and create if not existing
        self.calcdir = self.casm_directories.calctype_dir(configdir,self.casm_settings.default_clex)
        try:
            os.mkdir(self.calcdir)
        except:
            pass


        # read the settings json file
        print "  Reading relax.json settings file"
        sys.stdout.flush()
        setfile = self.casm_directories.settings_path_crawl("relax.json",self.casm_settings.default_clex,self.configdir)

        if setfile == None:
            raise vaspwrapper.VaspWrapperError("Could not find \"relax.json\" in an appropriate \"settings\" directory")
            sys.stdout.flush()

        else:
            print "Using "+str(setfile)+" as settings..."

        self.settings = vaspwrapper.read_settings(setfile)

        # add required keys to settings if not present
        if not "ncore" in self.settings:
            self.settings["ncore"] = None
        if not "npar" in self.settings:
            self.settings["npar"] = None
        if not "kpar" in self.settings:
            self.settings["kpar"] = None
        if not "vasp_cmd" in self.settings:
            self.settings["vasp_cmd"] = None
        if not "ncpus" in self.settings:
            self.settings["ncpus"] = None
        if not "run_limit" in self.settings:
            self.settings["run_limit"] = None



        self.auto = auto
        self.sort = sort
        print "VASP Relax object constructed\n"
        sys.stdout.flush()


    def setup(self):
        """ Setup initial relaxation run

            Uses the following files from the most local .../settings/calctype.name directory:
                INCAR: VASP input settings
                KPOINTS: VASP kpoints settings
                POSCAR: reference for KPOINTS if KPOINTS mode is not A/AUTO/Automatic
                SPECIES: info for each species such as which POTCAR files to use, MAGMOM, GGA+U, etc.

            Uses the following files from the .../config directory:
                POS: structure of the configuration to be relaxed

        """
        # Find required input files in CASM project directory tree
        vaspfiles=casm.vaspwrapper.vasp_input_file_names(self.casm_directories,self.casm_settings.default_clex,self.configdir)
        incarfile,prim_kpointsfile,prim_poscarfile,super_poscarfile,speciesfile=vaspfiles


        # Find optional input files
        extra_input_files = []
        for s in self.settings["extra_input_files"]:
            extra_input_files.append(self.casm_directories.settings_path_crawl(s,self.casm_settings.default_clex,self.configdir))
            if extra_input_files[-1] is None:
                raise vasp.VaspError("Relax.setup failed. Extra input file " + s + " not found in CASM project.")
        if self.settings["initial"]:
            extra_input_files += [ self.casm_directories.settings_path_crawl(self.settings["initial"],self.casm_settings.default_clex,self.configdir) ]
            if extra_input_files[-1] is None:
                raise vasp.VaspError("Relax.setup failed. No initial INCAR file " + self.settings["initial"] + " found in CASM project.")
        if self.settings["final"]:
            extra_input_files += [ self.casm_directories.settings_path_crawl(self.settings["final"],self.casm_settings.default_clex,self.configdir) ]
            if extra_input_files[-1] is None:
                raise vasp.VaspError("Relax.setup failed. No final INCAR file " + self.settings["final"] + " found in CASM project.")


        sys.stdout.flush()

        vasp.io.write_vasp_input(self.calcdir, incarfile, prim_kpointsfile, prim_poscarfile, super_poscarfile, speciesfile, self.sort, extra_input_files,self.settings["strict_kpoints"])


    def submit(self):
        """Submit a PBS job for this VASP relaxation"""

        # first, check if the job has already been submitted and is not completed
        db = pbs.JobDB()
        print "rundir", self.calcdir
        id = db.select_regex_id("rundir", self.calcdir)
        print "id:", id
        sys.stdout.flush()
        if id != []:
            for j in id:
                job = db.select_job(j)
                # taskstatus = ["Incomplete","Complete","Continued","Check","Error:.*","Aborted"]
                # jobstatus = ["C","Q","R","E","W","H","M"]
                if job["jobstatus"] != "C":
                    print "JobID:", job["jobid"], "  Jobstatus:", job["jobstatus"], "  Not submitting."
                    sys.stdout.flush()
                    return
                #elif job["taskstatus"] in ["Complete", "Check"] or re.match( "Error:.*", job["taskstatus"]):
                #    print "JobID:", job["jobid"], "  Taskstatus:", job["taskstatus"], "  Not submitting."
                #    sys.stdout.flush()
                #    return


        # second, only submit a job if relaxation status is "incomplete"

        # construct the Relax object
        relaxation = vasp.Relax(self.calcdir, self.run_settings())

        # check the current status
        (status, task) = relaxation.status()

        if status == "complete":
            print "Status:", status, "  Not submitting."
            sys.stdout.flush()

            # ensure job marked as complete in db
            if self.auto:
                for j in id:
                  job = db.select_job(j)
                  if job["taskstatus"] == "Incomplete":
                      try:
                          pbs.complete_job(jobid=j)
                      except (pbs.PBSError, pbs.JobDBError, pbs.EligibilityError) as e:
                          print str(e)
                          sys.stdout.flush()

            # ensure results report written
            if not os.path.isfile(os.path.join(self.calcdir, "properties.calc.json")):
                self.finalize()

            return

        elif status == "not_converging":
            print "Status:", status, "  Not submitting."
            sys.stdout.flush()
            return

        elif status != "incomplete":
            raise vaspwrapper.VaspWrapperError("unexpected relaxation status: '" + status + "' and task: '" + task + "'")
            sys.stdout.flush()
            return


        print "Preparing to submit a VASP relaxation PBS job"
        sys.stdout.flush()

        # cd to configdir, submit jobs from configdir, then cd back to currdir
        currdir = os.getcwd()
        os.chdir(self.calcdir)

        # determine the number of atoms in the configuration
        print "  Counting atoms in the POSCAR"
        sys.stdout.flush()
        pos = vasp.io.Poscar(os.path.join(self.configdir,"POS"))
        N = len(pos.basis)

        print "  Constructing a PBS job"
        sys.stdout.flush()
        # construct a pbs.Job
        job = pbs.Job(name=casm.jobname(self.configdir),\
                      account=self.settings["account"],\
                      nodes=int(math.ceil(float(N)/float(self.settings["atom_per_proc"])/float(self.settings["ppn"]))),\
                      ppn=int(self.settings["ppn"]),\
                      walltime=self.settings["walltime"],\
                      pmem=self.settings["pmem"],\
                      qos=self.settings["qos"],\
                      queue=self.settings["queue"],\
                      message=self.settings["message"],\
                      email=self.settings["email"],\
                      priority=self.settings["priority"],\
                      command="python -c \"import casm.vaspwrapper; casm.vaspwrapper.Relax('" + self.configdir + "').run()\"",\
                      auto=self.auto)

        print "  Submitting"
        sys.stdout.flush()
        # submit the job
        job.submit()
        self.report_status("submitted")

        # return to current directory
        os.chdir(currdir)

        print "CASM VASPWrapper relaxation PBS job submission complete\n"
        sys.stdout.flush()


    def run_settings(self):
        """ Set default values based on runtime environment"""
        settings = dict(self.settings)

        # set default values

        if settings["npar"] == "CASM_DEFAULT":
            if "PBS_NUM_NODES" in os.environ:
                settings["npar"] = int(os.environ["PBS_NUM_NODES"])
            else:
                settings["npar"] = None
        elif settings["npar"] == "VASP_DEFAULT":
            settings["npar"] = None

        if settings["npar"] == None:
            if settings["ncore"] == "CASM_DEFAULT":
                if "PBS_NUM_PPN" in os.environ:
                    settings["ncore"] = int(os.environ["PBS_NUM_PPN"])
                else:
                    settings["ncore"] = None
            elif settings["ncore"] == "VASP_DEFAULT":
                settings["ncore"] = 1
        else:
            settings["ncore"] = None

        if settings["ncpus"] == None or settings["ncpus"] == "CASM_DEFAULT":
            if "PBS_NP" in os.environ:
                settings["ncpus"] = int(os.environ["PBS_NP"])
            else:
                settings["ncpus"] = None

        if settings["run_limit"] == None or settings["run_limit"] == "CASM_DEFAULT":
            settings["run_limit"] = 10

        return settings


    def run(self):
        """ Setup input files, run a vasp relaxation, and report results """

        # construct the Relax object
        relaxation = vasp.Relax(self.calcdir, self.run_settings())

        # check the current status
        (status, task) = relaxation.status()


        if status == "complete":
            print "Status:", status
            sys.stdout.flush()

            # mark job as complete in db
            if self.auto:
                try:
                    pbs.complete_job()
                except (pbs.PBSError, pbs.JobDBError, pbs.EligibilityError) as e:
                    print str(e)
                    sys.stdout.flush()

            # write results to properties.calc.json
            self.finalize()
            return

        elif status == "not_converging":
            print "Status:", status
            self.report_status("failed","run_limit")
            print "Returning"
            sys.stdout.flush()
            return

        elif status == "incomplete":

            if task == "setup":
                self.setup()

            self.report_status("started")
            (status, task) = relaxation.run()

        else:
            self.report_status("failed","unknown")
            raise vaspwrapper.VaspWrapperError("unexpected relaxation status: '" + status + "' and task: '" + task + "'")
            sys.stdout.flush()


        # once the run is done, update database records accordingly

        if status == "not_converging":

            # mark error
            if self.auto:
                try:
                    pbs.error_job("Not converging")
                except (pbs.PBSError, pbs.JobDBError) as e:
                    print str(e)
                    sys.stdout.flush()

            print "Not Converging!"
            sys.stdout.flush()
            self.report_status("failed","run_limit")

            # print a local settings file, so that the run_limit can be extended if the
            #   convergence problems are fixed
            try:
                os.makedirs(self.casm_directories.configuration_calc_settings_dir(self.casm_settings.default_clex))
            except:
                pass
            settingsfile = os.path.join(self.casm_directories.configuration_calc_settings_dir(self.casm_settings.default_clex), "relax.json")
            vaspwrapper.write_settings(self.settings, settingsfile)

            print "Writing:", settingsfile
            print "Edit the 'run_limit' property if you wish to continue."
            sys.stdout.flush()
            return

        elif status == "complete":

            # mark job as complete in db
            if self.auto:
                try:
                    pbs.complete_job()
                except (pbs.PBSError, pbs.JobDBError, pbs.EligibilityError) as e:
                    print str(e)
                    sys.stdout.flush()

            # write results to properties.calc.json
            self.finalize()

        else:
            self.report_status("failed","unknown")
            raise vaspwrapper.VaspWrapperError("vasp relaxation complete with unexpected status: '" + status + "' and task: '" + task + "'")
            sys.stdout.flush()

    def report_status(self, status, failure_type=None):
        """Report calculation status to status.json file in configuration directory.

        Args:
            status: string describing calculation status. Currently used values are
                 not_submitted
                 submitted
                 complete
                 failed
             failure_type: optional string describing reason for failure. Currently used values are
                 unknown
                 electronic_convergence
                 run_limit"""

        output = dict()
        output["status"] = status
        if failure_type is not None:
            output["failure_type"] = failure_type

        outputfile = os.path.join(self.calcdir, "status.json")
        with open(outputfile, 'w') as file:
            file.write(json.dumps(output, file, cls=casm.NoIndentEncoder, indent=4, sort_keys=True))
        print "Wrote " + outputfile
        sys.stdout.flush()

    def finalize(self):
      if self.is_converged():
        # write properties.calc.json
        vaspdir = os.path.join(self.calcdir, "run.final")
	super_poscarfile = os.path.join(self.configdir,"POS")
        speciesfile = self.casm_directories.settings_path_crawl("SPECIES",self.casm_settings.default_clex,self.configdir)
        output = self.properties(vaspdir, super_poscarfile, speciesfile)
        outputfile = os.path.join(self.calcdir, "properties.calc.json")
        with open(outputfile, 'w') as file:
            file.write(json.dumps(output, file, cls=casm.NoIndentEncoder, indent=4, sort_keys=True))
        print "Wrote " + outputfile
        sys.stdout.flush()
        self.report_status('complete')

    def is_converged(self):
      # Check for electronic convergence in completed calculations. Returns True or False.

      # Verify that the last relaxation reached electronic convergence
      relaxation = vasp.Relax(self.calcdir, self.run_settings())
      for i in range(len(relaxation.rundir)):
        try:
          vrun = vasp.io.Vasprun( os.path.join(self.calcdir, relaxation.rundir[-i-1], "vasprun.xml"))
          if len(vrun.all_e_0[-1]) >= vrun.nelm:
            print('The last relaxation run (' +
                os.path.basename(relaxation.rundir[-i-1]) +
                ') failed to achieve electronic convergence; properties.calc.json will not be written.\n')
            self.report_status('failed','electronic_convergence')
            return False
          break
        except:
          pass

      # Verify that the final static run reached electronic convergence
      vrun = vasp.io.Vasprun( os.path.join(self.calcdir, "run.final", "vasprun.xml") )
      if len(vrun.all_e_0[0]) >= vrun.nelm:
          print('The final run failed to achieve electronic convergence; properties.calc.json will not be written.\n')
          self.report_status('failed','electronic_convergence')
          return False

      return True

    @staticmethod
    def properties(vaspdir, super_poscarfile = None, speciesfile = None):
        """Report results to properties.calc.json file in configuration directory, after checking for electronic convergence."""

        output = dict()
        vrun = vasp.io.Vasprun( os.path.join(vaspdir, "vasprun.xml") )

        # the calculation is run on the 'sorted' POSCAR, need to report results 'unsorted'

        if (super_poscarfile is not None) and (speciesfile is not None):
            species_settings = vasp.io.species_settings(speciesfile)
            super = vasp.io.Poscar(super_poscarfile, species_settings)
            unsort_dict = super.unsort_dict()
        else:
            # fake unsort_dict (unsort_dict[i] == i)
            unsort_dict = dict(zip(range(0,len(vrun.basis)),range(0,len(vrun.basis))))
	    super = vasp.io.Poscar(os.path.join(vaspdir,"POSCAR"))

        # unsort_dict:
        #   Returns 'unsort_dict', for which: unsorted_dict[orig_index] == sorted_index;
        #   unsorted_dict[sorted_index] == orig_index
        #   For example:
        #     'unsort_dict[0]' returns the index into the unsorted POSCAR of the first atom in the sorted POSCAR


        output["atom_type"] = super.type_atoms
        output["atoms_per_type"] = super.num_atoms
        output["coord_mode"] = vrun.coord_mode

        # as lists
        output["relaxed_forces"] = [ None for i in range(len(vrun.forces))]
        for i, v in enumerate(vrun.forces):
            output["relaxed_forces"][unsort_dict[i] ] = casm.NoIndent(vrun.forces[i])

        output["relaxed_lattice"] = [casm.NoIndent(v) for v in vrun.lattice]

        output["relaxed_basis"] = [ None for i in range(len(vrun.basis))]
        for i, v in enumerate(vrun.basis):
            output["relaxed_basis"][unsort_dict[i] ] = casm.NoIndent(vrun.basis[i])

        output["relaxed_energy"] = vrun.total_energy

	return output


