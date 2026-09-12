"""Software for tomography scanning with EPICS at APS beamline 19-BM

   Classes
   -------
   TomoScan19BM
     Derived class for tomography scanning with EPICS at APS beamline 19-BM
"""
import time

from epics import PV
from pathlib import Path

from tomoscan.tomoscan import ScanAbortError
from tomoscan.tomoscan_pso import TomoScanPSO
from tomoscan import log

EPSILON = .001

# Sensor readout time in seconds for the Vieworks VP-61MX.
#
# TomoScan.compute_frame_time() keys its readout table off the camera model and
# knows nothing about this one, so a readout time has to be supplied here.  The
# ADEuresys driver publishes no readout-time record to prefer over it -- unlike
# ADKinetix at 32-ID-C, the only GenICam timing features on this camera are
# GC_AcqFrameRate and GC_AcqLineRate -- so this constant is the only source.
#
# TODO: this value has NOT been measured.  It is a deliberately conservative
# placeholder: too long only makes a scan slower, too short drops frames.
# Measure it the way the tables in TomoScan.compute_frame_time() were built --
# minimum exposure, a few thousand frames, the fastest trigger rate that drops
# nothing -- and reduce it.  As a cross-check, 6380 rows divided by
# GC_AcqLineRate_RBV should land near the true value.
VIEWORKS_READOUT_TIME = 0.060
VIEWORKS_READOUT_MARGIN = 1.05

# Model string reported by 19bmVieworks:cam1:Model_RBV.
VIEWORKS_MODEL = 'VP-61MX-M18H0'

# Sense of the ShutterStatus PV.
#
# 19-BM reads its front-end shutter through S19BM-PSS:FES:BeamBlockingM, which
# reports whether the beam is BLOCKED.  That is the inverse of the
# PA:...:STA_?_SBS_OPEN_PL records used at 32-ID, where 1 means open, and the
# same convention 2-BM-B uses with S02BM-PSS:SBS:BeamBlockingM.  Getting this
# backwards does not fail loudly: the scan simply waits out its timeout with
# the shutter already in the state it asked for.
SHUTTER_BLOCKED = 1      # beam off, shutter closed
SHUTTER_NOT_BLOCKED = 0  # beam on, shutter open


class TomoScan19BM(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 19-BM

    19-BM collects with a Vieworks VP-61MX on a Euresys Coaxlink Quad CXP-12
    frame grabber, driven by the areaDetector ADEuresys driver, and triggers it
    from the PSO output of an Aerotech Ensemble rotation stage -- the same stage
    and controller previously used at 7-BM.

    It is derived from tomoscan_32idc, which is the closest working station, but
    differs from it in four ways:

    - There is a fast shutter.  32-ID-C has none, so its open_shutter() and
      close_shutter() are no-ops; here they follow tomoscan_7bm and drive both
      the front-end shutter and the fast shutter.
    - There is no mctoptics server.  32-ID-C indexes pv_prefixes['MctOptics']
      unconditionally in __init__, which would be a KeyError here, and uses it
      to switch between two cameras.  All of that is removed, along with
      reinit_camera() and the CameraSelect callback.
    - The camera is a GenICam device.  ADKinetix is not, so 32-ID-C's
      set_trigger_mode() and its Kinetix readout constant do not apply.
    - There is no web camera and no PDU, so no ~/access.json is read.

    Three pieces are carried over from tomoscan_32idc deliberately, because each
    fixes a failure that cost real data there and none of them is specific to
    that station: check_rotation_ready(), queue_pv() and flush_file_plugin().
    Their docstrings explain what each one is for.

    Not carried over is 32-ID-C's wait_camera_done() override, which exists
    because the Kinetix ignores an occasional PSO trigger.  There is no evidence
    the Vieworks does; if long scans start ending in unexplained camera
    timeouts, that override is the first thing to bring across.  Until then
    triggers_exhausted stays False, which flush_file_plugin() handles by using
    its longer, more conservative settling time.

    Parameters
    ----------
    pv_files : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pv_files
    """

    def __init__(self, pv_files, macros):
        super().__init__(pv_files, macros)

        # Rotation motor fields the base class does not define.  Needed by
        # check_rotation_ready(); see the comments there.
        rotation_pv_name = self.control_pvs['Rotation'].pvname
        self.epics_pvs['RotationDHLM'] = PV(rotation_pv_name + '.DHLM')
        self.epics_pvs['RotationDLLM'] = PV(rotation_pv_name + '.DLLM')
        self.epics_pvs['RotationHLM']  = PV(rotation_pv_name + '.HLM')
        self.epics_pvs['RotationLLM']  = PV(rotation_pv_name + '.LLM')
        self.epics_pvs['RotationLVIO'] = PV(rotation_pv_name + '.LVIO')

        # Read by flush_file_plugin().  Only 32-ID-C's wait_camera_done()
        # override ever sets it True, and that override is not carried over, so
        # here it stays False and the flush always uses its conservative settle.
        self.triggers_exhausted = False

        # GenICam camera records the base class only creates for Point Grey,
        # FLIR, Adimec and Mikrotron cameras.  CamManufacturer reads "VIEWORKS",
        # which matches none of those tests, so set_trigger_mode_vieworks()
        # would raise KeyError on every one of these without this block.
        camera_prefix = self.pv_prefixes['Camera'] + 'cam1:'
        self.control_pvs['CamTriggerSource']    = PV(camera_prefix + 'TriggerSource')
        self.control_pvs['CamExposureMode']     = PV(camera_prefix + 'ExposureMode')
        self.control_pvs['CamArrayCallbacks']   = PV(camera_prefix + 'ArrayCallbacks')
        self.control_pvs['CamFrameRateEnable']  = PV(camera_prefix + 'FrameRateEnable')
        self.control_pvs['CamPixelFormat']      = PV(camera_prefix + 'PixelFormat')
        self.control_pvs['CamUniqueIdMode']     = PV(camera_prefix + 'UniqueIdMode')
        self.epics_pvs = {**self.config_pvs, **self.control_pvs}

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Disable over writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        # NOTE: no NDAttributes or HDF5 layout files are set here.  32-ID-C
        # points CamNDAttributesFile and FPXMLFileName at mctDetectorAttributes
        # .xml / mctLayout.xml, which read six PVs from the mctoptics server.
        # 19-BM has no such server and no equivalent pair of files yet, and
        # naming a file that does not exist only sets NDAttributesStatus to
        # "File not found".  When the 19-BM files are written, set them here.

        log.setup_custom_logger("./tomoscan.log")

    def open_shutter(self):
        """Opens the shutters to collect flat fields or projections.

        Follows tomoscan_7bm: the front-end shutter is opened first and waited
        on, then the fast shutter.  Both are skipped in testing mode.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
            return

        # Front-end shutter
        if not self.epics_pvs['OpenShutter'] is None:
            pv = self.epics_pvs['OpenShutter']
            value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
            log.info('open shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            self.wait_frontend_shutter_open()
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)

        # Fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)

    def close_shutter(self):
        """Closes the shutters to collect dark fields and at the end of a scan.

        The fast shutter is closed first and not waited on -- it is the fast one,
        and the front-end close that follows takes far longer than it does.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
            return

        # Fast shutter
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=False)

        # Front-end shutter
        if not self.epics_pvs['CloseShutter'] is None:
            pv = self.epics_pvs['CloseShutter']
            value = self.epics_pvs['CloseShutterValue'].get(as_string=True)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
            log.info('close shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseShutter'].put(value, wait=True)
            self.wait_pv(self.epics_pvs['ShutterStatus'], SHUTTER_BLOCKED)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)

    def wait_frontend_shutter_open(self, timeout=-1):
        """Waits for the front-end shutter to open, retrying the open command.

        Every beamline class defines its own copy of this -- it is not in the
        base class -- so ``open_shutter()`` above would raise AttributeError
        without it.

        The wait is for ``ShutterStatus == SHUTTER_NOT_BLOCKED``.  Note this
        cannot follow the 32-ID-C version, which waits for the status to equal
        ``OpenShutterValue``: that works only where the readback is an
        ``..._OPEN_PL`` record whose 1 means open.  Here the readback is
        ``BeamBlockingM``, so 1 means the opposite and comparing against the
        command value would wait for the shutter to close.

        Parameters
        ----------
        timeout : float
            Maximum number of seconds to wait.  Negative means wait forever.

        Raises
        ------
        ScanAbortError
            If ``abort_scan()`` is called, or the timeout expires.
        """
        start_time = time.time()
        pv = self.epics_pvs['OpenShutter']
        value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
        log.info('open shutter: %s, value: %s', pv, value)
        elapsed_time = 0
        while True:
            if self.epics_pvs['ShutterStatus'].get() == SHUTTER_NOT_BLOCKED:
                log.info('shutter is open in %f s', elapsed_time)
                return
            # The other beamline classes call exit() here.  In the scan thread
            # that raises SystemExit, which kills the thread silently and leaves
            # the server unable to start another scan.  ScanAbortError is what
            # the rest of this class raises and what fly_scan() already handles.
            if not self.scan_is_running:
                raise ScanAbortError
            value = self.epics_pvs['OpenShutterValue'].get()
            time.sleep(1.0)
            elapsed_time = time.time() - start_time
            log.warning('waiting on shutter to open: %f s', elapsed_time)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            if 0 < timeout <= elapsed_time:
                log.error('shutter did not open within %s s', timeout)
                raise ScanAbortError

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode of the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
        """
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if camera_model == VIEWORKS_MODEL:
            self.set_trigger_mode_vieworks(trigger_mode, num_images)
        else:
            log.error('Camera %s is not supported', camera_model)
            exit(1)

    def set_trigger_mode_vieworks(self, trigger_mode, num_images):
        """Sets the trigger mode for the Vieworks VP-61MX (ADEuresys/ADGenICam).

        Modelled on tomoscan_2bm's Oryx path, since both are GenICam cameras,
        with two differences that come from the features this camera actually
        publishes:

        - ``TriggerOverlap`` is **not** set.  Its only choice is "N.A." on this
          camera, so writing "ReadOut" as the Oryx path does would fail.
        - ``TriggerSource`` comes from the ``ExternalTriggerSource`` PV rather
          than a literal.  The choices here are Software, UserOutput0,
          LinkTrigger0, Timer0Active and Line0, and the PSO pulse arrives on
          Line0; keeping it in a PV means rewiring does not need a code change.

        ``GC_TriggerSelector`` is left alone: its only choice is ExposureStart.
        ``GC_TriggerActivation`` is likewise left at RisingEdge, which is what
        the PSO output produces.
        """
        self.epics_pvs['CamAcquire'].put('Done')
        self.wait_pv(self.epics_pvs['CamAcquire'], 0)
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else:  # PSOExternal
            # Turn triggering off first: several of the settings below cannot be
            # changed while the camera is armed, and the scan may have aborted
            # with the camera in any state.
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            trigger_source = self.epics_pvs['ExternalTriggerSource'].get(as_string=True)
            self.epics_pvs['CamTriggerSource'].put(trigger_source, wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)
            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)

    def compute_frame_time(self):
        """Computes the time to collect and read out an image from the Vieworks.

        TomoScan.compute_frame_time() keys a hardcoded table off the camera
        model and has no entry for this one.  Worse than merely returning
        nothing, it would raise: ``pixel_format`` is only bound inside the
        per-model branches, so with no branch taken the ``log.error`` that
        reports the unsupported camera raises UnboundLocalError while
        formatting its own message.  The base class docstring directs
        single-beamline cameras to override here, which is what this does.

        Any other camera is handed back to the base class.
        """
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if camera_model != VIEWORKS_MODEL:
            return super().compute_frame_time()

        exposure = self.epics_pvs['CamAcquireTimeRBV'].value
        frame_time = exposure * VIEWORKS_READOUT_MARGIN
        if frame_time < VIEWORKS_READOUT_TIME:
            frame_time = VIEWORKS_READOUT_TIME + .001
        self.readout_margin = VIEWORKS_READOUT_MARGIN
        return frame_time

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Sets the data directory.

        - Calls the base class method.

        - Verifies the rotation stage can perform the scan.
        """
        log.info('begin scan')

        self.triggers_exhausted = False

        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True))
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

        # Call the base class method
        super().begin_scan()

        # Refuse to start a scan the rotation stage cannot actually perform
        self.check_rotation_ready()

    def check_rotation_ready(self):
        """Verifies that the rotation stage can perform the scan about to start.

        Called from ``begin_scan()`` once ``super().begin_scan()`` has returned,
        which is the first moment at which both things this checks are known:
        ``program_PSO()`` has moved the stage to ``rotation_start_new``, and
        ``compute_positions_PSO()`` has published the taxi positions the fly move
        will run between.

        Two independent failures are caught:

        1. **The pre-positioning move did not arrive.**  ``program_PSO()`` puts to
           ``Rotation`` with ``wait=True``, but a completion callback says only
           that the record finished processing, not that the stage got there.  A
           refused move, a disabled amplifier or a dead controller link all
           satisfy the wait and leave the stage where it was.  Comparing the
           readback against the demand is agnostic to which of those happened.

        2. **The fly move will be refused for violating a soft limit.**  At
           32-ID-C this cost 24 consecutive empty datasets and 9.5 h of
           unattended running.  ``end_scan()`` returns the stage to zero by
           redefining the current angle modulo 360 rather than unwinding it, so
           with finite *dial* limits the dial marches a full turn per scan until
           the fly move no longer fits.  The motor record then refuses it
           silently: nothing turns, the PSO never fires, and the only symptom is
           ``ERROR: Camera timeout`` twenty minutes later with dark and flat
           fields already written.  Checking the taxi endpoints before the scan
           turns that into an immediate, named abort.

        The two checks cover different things and both are cheap: check 1 alone
        would not have caught the 32-ID-C failure, because the short
        pre-positioning move fitted inside the remaining travel and completed
        normally; it was the 360 deg fly move that did not fit.

        Raises
        ------
        ScanAbortError
            If the stage is not where it was sent, or if either taxi endpoint
            lies outside an enforced soft limit.
        """
        # program_PSO() is skipped for these, so there is no move to verify and
        # no taxi position to check.
        if self.num_angles <= 0 or not self.epics_pvs['ProgramPSO'].get():
            return

        # 1. Did the pre-positioning move actually arrive?
        #
        # The tolerance is deliberately loose: this is looking for a move that
        # did not happen, which misses by the whole move distance, not for a
        # settling error.
        rbv = self.epics_pvs['RotationRBV'].get()
        tolerance = max(0.01, abs(self.rotation_step))
        if rbv is None or abs(rbv - self.rotation_start_new) > tolerance:
            lvio = self.epics_pvs['RotationLVIO'].get()
            log.error('Rotation stage did not reach the scan start position: '
                      'demanded %s, readback %s (.LVIO = %s)',
                      self.rotation_start_new, rbv, lvio)
            if lvio:
                log.error('.LVIO is set, so the motor record refused the move. '
                          'Check the soft limits on %s',
                          self.control_pvs['Rotation'].pvname)
            raise ScanAbortError

        # 2. Will the fly move be refused for violating a soft limit?
        #
        # Replicate the motor record's own rule (motorRecord.cc): an all-zero
        # *dial* limit pair means limit checking is off, and the .HLM / .LLM
        # fields then still report stale values that no longer constrain
        # anything.  A continuously rotating axis is normally configured that
        # way on purpose, so a naive "target within [.LLM, .HLM]" test would
        # reject every scan on a correctly configured stage.
        dhlm = self.epics_pvs['RotationDHLM'].get()
        dllm = self.epics_pvs['RotationDLLM'].get()
        if dhlm is None or dllm is None or (dhlm == 0 and dllm == 0):
            return

        hlm = self.epics_pvs['RotationHLM'].get()
        llm = self.epics_pvs['RotationLLM'].get()
        if hlm is None or llm is None:
            return

        start_taxi = self.epics_pvs['PSOStartTaxi'].get()
        end_taxi   = self.epics_pvs['PSOEndTaxi'].get()
        span = (abs(end_taxi - start_taxi)
                if start_taxi is not None and end_taxi is not None else None)
        for name, target in (('start', start_taxi), ('end', end_taxi)):
            if target is None:
                continue
            if target > hlm or target < llm:
                log.error('Rotation %s taxi position %.4f is outside the soft '
                          'limits [%.4f, %.4f]; the motor record would refuse '
                          'the move and the scan would fail as a camera '
                          'timeout.', name, target, llm, hlm)
                log.error('Travel remaining from the current position %.4f deg '
                          'is [%.4f, %+.4f] and this scan needs %s deg. Set '
                          '.DHLM = .DLLM = 0 on %s to disable soft-limit '
                          'checking on this continuously rotating axis.',
                          rbv, llm - rbv, hlm - rbv,
                          'an unknown number of' if span is None
                          else '%.4f' % span,
                          self.control_pvs['Rotation'].pvname)
                raise ScanAbortError

    def queue_pv(self, name):
        """Returns the file plugin queue PV ``name``, creating it if necessary.

        ``FPQueueFree`` and ``FPQueueSize`` are not among the PVs the base class
        registers.  Indexing ``epics_pvs`` for them directly raised ``KeyError``
        inside ``end_scan()`` at 32-ID-C, killing the ``fly_scan`` thread before
        ``add_theta()`` ran and leaving a complete 60000-projection dataset with
        no ``exchange/theta``.  Worse, the dead thread left the server unable to
        start another scan at all.

        So resolve them here instead of trusting registration.  The prefix comes
        off an FP PV the base class always provides, which keeps this correct if
        the file plugin has been repointed at another camera.  A failure to
        resolve returns ``None`` and the caller treats that exactly like an
        unreadable readback -- the flush falls back to the progress/stall path,
        which is slower but always safe.
        """
        pv = self.epics_pvs.get(name)
        if pv is not None:
            return pv
        # Remember a failure as well as a success.  This is called once per PV on
        # every poll of a loop that can run for a minute, so an un-cached failure
        # would repeat its warning several hundred times per scan.
        if getattr(self, 'queue_pv_unresolved', False):
            return None
        suffix = 'NumCaptured_RBV'
        try:
            anchor = self.epics_pvs['FPNumCaptured'].pvname
        except (KeyError, AttributeError):
            self.queue_pv_unresolved = True
            return None
        # Only trust the anchor if it really is the PV we think it is.  Slicing a
        # fixed length off a name that does not end that way yields a plausible
        # looking prefix pointing at nothing, and a PV that never connects reads
        # as None forever -- a silent permanent fallback rather than a clean one.
        if not isinstance(anchor, str) or not anchor.endswith(suffix):
            log.warning('cannot derive the file plugin prefix from %r, '
                        'flushing without the queue readbacks', anchor)
            self.queue_pv_unresolved = True
            return None
        pv = PV(anchor[:-len(suffix)] + name[len('FP'):])
        self.epics_pvs[name] = pv
        self.control_pvs[name] = pv
        return pv

    def flush_file_plugin(self, stall_timeout=60.0, idle_stall_timeout=10.0,
                          poll_interval=0.5, report_interval=5.0,
                          settle_time=1.0):
        """Waits for the HDF5 file plugin to write out everything it has queued.

        The camera can deliver frames faster than the disk absorbs them.  ADCore
        takes up the difference in the file plugin's input queue, so when a scan
        ends the plugin can still be thousands of frames behind.  Writing
        ``Capture = Done`` at that moment reaches ``NDPluginFile::doCapture(0)``,
        which closes the file straight away; the queued frames are then popped with
        capture off, dropped, and never written.  They are not counted in
        ``DroppedArrays`` either, so the loss leaves no trace beyond a short file.

        This matters more at 19-BM than at the station this came from: a
        VP-61MX frame is 122 MB, roughly six times a Kinetix frame, so the
        plugin falls behind faster and has more to write out at the end.

        This method waits for the backlog to drain first.  The condition it waits
        for is that the queue is *empty* and the written count has stopped moving
        (``QueueFree == QueueSize``, ``NumCaptured_RBV`` unchanged): nothing is
        pending and nothing more is arriving, so the flush is genuinely finished.
        That is the only signal that is true regardless of how many frames the
        scan actually produced.

        Note that ``CamAcquireBusy == 0`` cannot be part of that test.  This runs
        before anything stops the camera, so requiring it would make the queue
        test unsatisfiable whenever the camera finishes a scan still armed.  It
        is used only to choose how long the queue must stay empty.

        Progress is still tracked as the fallback, for the case where the queue
        readbacks are unavailable or the plugin wedges with frames still in hand:
        as long as ``NumCaptured_RBV`` keeps advancing it keeps waiting, and it
        gives up once the count has not moved for ``stall_timeout`` seconds.

        The plugin closes the file itself once it has written ``NumCapture``
        frames, so in the normal case this returns as soon as that happens and the
        ``Capture = Done`` that follows is a no-op.

        On an aborted scan ``abort_scan()`` has already stopped the plugin, so this
        returns immediately and an abort still discards the backlog as before.

        Parameters
        ----------
        stall_timeout : float
            Seconds without progress before giving up and closing the file anyway,
            used while the camera is still acquiring.
        idle_stall_timeout : float
            Shorter no-progress timeout used once the camera has stopped, when no
            further frames can arrive.  Also how long the queue must stay empty
            while the camera still reports busy.
        poll_interval : float
            Seconds between polls of ``NumCaptured_RBV``.
        report_interval : float
            Seconds between progress messages while draining.
        settle_time : float
            Seconds the queue must stay empty, with the written count unchanged,
            before the flush is called finished, once the camera has stopped.
        """
        num_capture = self.epics_pvs['FPNumCapture'].get()
        num_captured = self.epics_pvs['FPNumCaptured'].get()
        if num_captured is None:
            log.error('flush_file_plugin: NumCaptured_RBV is not readable, not waiting')
            return

        if self.epics_pvs['FPCaptureRBV'].get() == 0:
            log.info('file plugin already finished, %s frames written', num_captured)
            return

        self.epics_pvs['ScanStatus'].put('Flushing file plugin')
        start_time = time.time()
        last_count = num_captured
        last_progress_time = start_time
        last_report_time = start_time

        drained = False
        empty_since = None
        empty_count = None
        while True:
            # The plugin closes the file on its own once NumCapture is reached
            if self.epics_pvs['FPCaptureRBV'].get() == 0:
                break

            num_captured = self.epics_pvs['FPNumCaptured'].get()
            if num_captured is None:
                num_captured = last_count
            now = time.time()

            # An empty queue whose written count has stopped moving means
            # everything that was ever going to arrive has been written.  This is
            # the normal exit.
            #
            # The queue reads empty the moment the plugin pops the last array,
            # which is before that frame is written, so the condition must hold
            # with the count unchanged for a settling period -- otherwise the
            # Capture = Done that follows could close the file mid-write and lose
            # the last frame, the very failure this method exists to prevent.  A
            # stopped camera makes that certain, so settle_time is enough; a
            # camera still reporting busy earns the longer wait.
            free_pv = self.queue_pv('FPQueueFree')
            size_pv = self.queue_pv('FPQueueSize')
            queue_free = free_pv.get() if free_pv is not None else None
            queue_size = size_pv.get() if size_pv is not None else None
            quiet = (self.epics_pvs['CamAcquireBusy'].get() == 0
                     or self.triggers_exhausted)

            if (queue_free is not None and queue_size is not None
                    and queue_free >= queue_size):
                settle = settle_time if quiet else idle_stall_timeout
                if empty_since is None or num_captured != empty_count:
                    empty_since, empty_count = now, num_captured
                elif now - empty_since >= settle:
                    drained = True
                    break
            else:
                empty_since = None

            if num_captured > last_count:
                last_count = num_captured
                last_progress_time = now
            else:
                # Nothing more can arrive once the camera has stopped, so a short
                # quiet period is enough to call the queue drained.  If the
                # readback is unavailable, assume it is still running and keep the
                # conservative timeout.
                if quiet:
                    timeout, camera_state = idle_stall_timeout, 'no longer sending frames'
                else:
                    timeout, camera_state = stall_timeout, 'acquiring'
                if now - last_progress_time >= timeout:
                    log.error('file plugin stalled at %s/%s frames for %.0f s '
                              'with the camera %s, closing the file anyway',
                              num_captured, num_capture, timeout, camera_state)
                    break

            if now - last_report_time >= report_interval:
                log.info('flushing file plugin: %s/%s', num_captured, num_capture)
                self.epics_pvs['ImagesSaved'].put(str(num_captured) + '/' + str(num_capture))
                last_report_time = now

            time.sleep(poll_interval)

        elapsed = time.time() - start_time
        num_captured = self.epics_pvs['FPNumCaptured'].get()
        if num_captured is None:
            num_captured = last_count
        self.epics_pvs['ImagesSaved'].put(str(num_captured) + '/' + str(num_capture))
        log.info('file plugin flushed %s/%s frames in %.1f s',
                 num_captured, num_capture, elapsed)
        if num_capture is not None and num_captured < num_capture:
            short = num_capture - num_captured
            if drained:
                # The queue emptied with the camera stopped, so every frame that
                # existed was written.  A short count here means the camera never
                # produced those frames, not that the file plugin lost them.
                log.info('file plugin wrote %s of the %s frames requested; the '
                         'queue drained completely, so the missing %s were never '
                         'produced by the camera rather than lost on the way to '
                         'disk', num_captured, num_capture, short)
            else:
                log.warning('file plugin wrote %s of %s frames, %s frames were '
                            'not saved', num_captured, num_capture, short)
