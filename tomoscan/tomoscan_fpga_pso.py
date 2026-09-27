"""Software for tomography scanning with EPICS

   Classes
   -------
   TomoScanFPGAPSO
     Derived class for tomography scanning with EPICS using Aerotech controllers with PSO and softGlueZynq FPGA trigger outputs
"""

import time
import os
import math
import numpy as np
from tomoscan.tomoscan import TomoScan, ScanAbortError, CameraTimeoutError
from tomoscan import log

class TomoScanFPGAPSO(TomoScan):
    """Derived class used for tomography scanning with EPICS using Aerotech controllers with PSO and softGlueZynq FPGA trigger outputs

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
        self.epics_pvs['ProgramPSO'].put('Yes')
        # On the A3200 we can read the number of encoder counts per rotation from the controller
        # Unfortunately the Ensemble does not support this
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        if (pso_model == 'A3200'):
            pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
            self.epics_pvs['PSOCommand.BOUT'].put("UNITSTOCOUNTS(%s, 360.0)" % pso_axis, wait=True, timeout=10.0)
            reply = self.epics_pvs['PSOCommand.BINP'].get(as_string=True)
            counts_per_rotation = float(reply[1:])
            self.epics_pvs['PSOCountsPerRotation'].put(counts_per_rotation)
        self.epics_pvs['CamUniqueIdMode'].put('Camera',wait=True)

        self.epics_pvs['InterlacedEfficiencyRequested'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['InterlacedNumAngles'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['InterlacedNumberOfRotation'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['InterlacedMode'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['InterlacedRotationStart'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['ExposureTime'].add_callback(self.pv_callback_efficiency)
        self.epics_pvs['TriggerSource'].add_callback(self.pv_callback_trigger_source)

    def pv_callback_efficiency(self, pvname=None, value=None, char_value=None, **kw):
        """Recompute scan preview PVs whenever any input parameter changes.

        Writes: RotationSpeed, MotionBlurr, InterlacedScanTime,
                InterlacedEfficiencyCalculated, DroppedFrames.
        No PSO/FPGA reprogramming — preview only.
        """
        log.debug('pv_callback_efficiency pvName=%s', pvname)
        if self.scan_is_running:
            return
        try:
            N    = int(self.epics_pvs['InterlacedNumAngles'].get())
            K    = int(self.epics_pvs['InterlacedNumberOfRotation'].get())
            mode = int(self.epics_pvs['InterlacedMode'].get())
            rotation_start = float(self.epics_pvs['InterlacedRotationStart'].get())
            rotation_stop  = float(self.epics_pvs['InterlacedRotationStop'].get())
            exposure_time  = float(self.epics_pvs['ExposureTime'].get())
            size_x         = int(self.control_pvs['ArraySizeX_RBV'].get())
            req_pct        = float(self.epics_pvs['InterlacedEfficiencyRequested'].get())

            if N <= 0 or K <= 0:
                return

            log.info('Preview inputs: N=%d K=%d mode=%d start=%.2f stop=%.2f exp=%.4f s size_x=%d req=%.1f%%',
                     N, K, mode, rotation_start, rotation_stop, exposure_time, size_x, req_pct)

            result = self._compute_scan_preview(
                N, K, mode, rotation_start, rotation_stop,
                exposure_time, size_x, req_pct)
            if result is None:
                return

            self.epics_pvs['RotationSpeed'].put(result['velocity'])
            self.epics_pvs['MotionBlurr'].put(result['blur_px'])
            self.epics_pvs['InterlacedScanTime'].put(result['scan_time'])
            self.epics_pvs['InterlacedEfficiencyCalculated'].put(result['efficiency'])
            self.epics_pvs['DroppedFrames'].put(result['dropped'])

            log.info('Preview: vel=%.4f°/s blur=%.2f px scan_time=%.1f s eff=%.1f%% dropped=%d',
                     result['velocity'], result['blur_px'], result['scan_time'],
                     result['efficiency'], result['dropped'])
        except Exception:
            log.error('pv_callback_efficiency failed', exc_info=True)

    def pv_callback_trigger_source(self, pvname=None, value=None, char_value=None, **kw):
        """Sync FPGAMUX2 whenever TriggerSource changes (e.g. from medm screen).
        TriggerSource=0 (PSO) -> MUX=0; TriggerSource=1 (FPGA) -> MUX=1.
        """
        try:
            mux_val = "1" if int(value) == 1 else "0"
            # Use wait=False: calling put(wait=True) inside a CA callback deadlocks
            # (the put-complete event needs the CA thread, which is stuck in this callback).
            self.epics_pvs['FPGAMUX2'].put(mux_val, wait=False)
            log.info('TriggerSource -> %s: FPGAMUX2 set to %s', value, mux_val)
        except Exception:
            log.error("pv_callback_trigger_source failed", exc_info=True)

    def _compute_scan_preview(self, N, K, mode, rotation_start, rotation_stop,
                              exposure_time, size_x, req_pct):
        """Compute scan preview parameters.

        Uses the same angle-generation functions as the actual scan so the
        preview is consistent with what the hardware will do.  Builds an
        efficiency table over all unique acquisition-order angular gaps and
        selects the last row whose efficiency meets req_pct.

        Returns dict with keys: velocity, blur_px, scan_time, efficiency
        or None if the mode/parameters are unsupported.
        """
        # Use the requested ExposureTime (already read from PV by the caller) plus the
        # readout margin set by the last successful compute_frame_time() call.
        # Avoids slow CamPixelFormat.get() calls; defaults to 1.01 (FLIR cameras).
        readout_margin = getattr(self, 'readout_margin', 1.01)
        frame_time = float(exposure_time) * readout_margin
        if frame_time <= 0:
            log.warning('_compute_scan_preview: exposure_time=%.4f s — set ExposureTime > 0 to enable preview', exposure_time)
            return None

        total_frames = N * K

        try:
            if mode == 0:
                flat = self.angles_uniform_multiturn_unwrapped(
                    N=N, K=K, start_deg=rotation_start, delta_theta=360.0/N)
            elif mode == 1:
                flat = self.angles_multitimbir_unwrapped(N=N, K=K, start_deg=rotation_start)
            elif mode == 2:
                flat = self.angles_goldenangle_unwrapped(N=N, K=K, start_deg=rotation_start)
            elif mode == 3:
                flat = self.angles_corput_unwrapped(N=N, K=K, start_deg=rotation_start)
            else:
                return None
        except Exception:
            log.warning('_compute_scan_preview: angle generation failed', exc_info=True)
            return None

        delta         = np.diff(flat)
        delta_rounded = np.round(delta, decimals=6)
        unique_dt     = np.sort(np.unique(delta_rounded))
        total_angle   = float(flat[-1] - flat[0])

        if len(unique_dt) == 0 or unique_dt[0] <= 0:
            return None

        rows = []
        for dt in unique_dt:
            vel       = dt / frame_time
            t_scan    = total_angle * frame_time / dt
            collected = 1 + int(np.sum(delta_rounded >= dt))
            dropped   = total_frames - collected
            eff       = 100.0 * collected / total_frames
            blur      = size_x * np.sin(np.radians(vel * exposure_time) / 2)
            rows.append(dict(velocity=vel, scan_time=t_scan, efficiency=eff,
                             blur_px=blur, dropped=dropped))

        req = float(req_pct)
        selected = None
        for row in rows:
            if row['efficiency'] >= req:
                selected = row    # keep last qualifying row
        return selected

    def collect_static_frames(self, num_frames):
        """Collects num_frames images in "Internal" trigger mode for dark fields and flat fields.

        Parameters
        ----------
        num_frames : int
            Number of frames to collect.
        """
        # This is called when collecting dark fields or flat fields

        log.info('collect static frames: %d', num_frames)
        self.set_trigger_mode('Internal', num_frames)
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        frame_time = self.compute_frame_time()
        collection_time = frame_time * num_frames
        self.wait_camera_done(collection_time + 5.0)

    def collect_dark_fields(self):
        """Collects dark field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumDarkFields`` PV.
        """

        log.info('collect dark fields')
        super().collect_dark_fields()
        self.collect_static_frames(self.num_dark_fields)

    def collect_flat_fields(self):
        """Collects flat field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumFlatFields`` PV.
        """
        log.info('collect flat fields')
        super().collect_flat_fields()
        self.collect_static_frames(self.num_flat_fields)


    def begin_scan(self):
        if self.scan_is_running:
            log.warning('begin_scan already in progress — ignoring duplicate call')
            return
        self.scan_is_running = True   # claim early; super().begin_scan() sets it again (harmless)
        log.info('begin scan')
        self.epics_pvs['ScanStatus'].put('Beginning scan')
        # NOTE: super().begin_scan() is called AFTER FPGA/PSO programming below.
        # It blocks ~30s on FPFilePath.put(wait=True); deferring it keeps FPGA
        # programming fast (matches original behaviour).
        #
        # super().begin_scan() normally sets self.max_rotation_speed from RotationMaxSpeed.
        # Read it here so PSO/FPGA programming (compute_positions_PSO, program_PSO4FPGA) can
        # use it; super() will re-read it later (harmless).
        self.max_rotation_speed = self.epics_pvs['RotationMaxSpeed'].value

        # Force FPGA trigger mode for this scan; reset to 0 in end_scan()
        self.epics_pvs['TriggerSource'].put(1, wait=True)
        self.epics_pvs['FPGAMUX2'].put("1", wait=True)

        log.info('Reading user inputs')
        size_x = self.control_pvs['ArraySizeX_RBV'].get()                               # detector horizontal size [pixels]
        mode = int(self.epics_pvs['InterlacedMode'].get())                               # 0..4
        self.rotation_start = float(self.epics_pvs['InterlacedRotationStart'].get())
        self.rotation_stop  = float(self.epics_pvs['InterlacedRotationStop'].get())      # needed by _compute_senses()
        N = int(self.epics_pvs['InterlacedNumAngles'].get())                             # images per rotation
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())                      # number of rotations
        self.num_angles = int(N * K)                                                     # total images
        req_pct = float(self.epics_pvs['InterlacedEfficiencyRequested'].get())           # 0..100
        req_eff = max(0.0, min(1.0, req_pct / 100.0))                                    # 0..1

        if self.num_angles > 0 and self.epics_pvs['ProgramPSO'].get():
            # Set rotary stage motor speed
            # Compute frame time and angular step sizes (used for speed/efficiency selection only,
            # not for PSO window sizing).
            frame_time = self.compute_frame_time()
            angles_deg, steps_deg = self.compute_interlaced_angles(mode, self.num_angles)
            min_step = float(np.min(steps_deg))
            max_step = float(np.max(steps_deg))

            if mode == 0:
                # Uniform: safe speed => 100% efficiency
                self.motor_speed = abs(min_step) / frame_time
                achieved = 1.0
                thr_deg = self.motor_speed * frame_time
            else:
                # Interlaced: fastest constant speed meeting requested efficiency
                self.motor_speed, achieved, thr_deg = self.choose_speed_for_efficiency(
                    steps_deg, frame_time, req_eff
                )
            self.epics_pvs['InterlacedEfficiencyCalculated'].put(achieved * 100.0, wait=True)
            log.info("Efficiency requested=%g%% calculated=%g%%", req_pct, achieved * 100.0)
            log.info("InterlacedMode=%d: min_step=%g deg, max_step=%g deg", mode, min_step, max_step)
            log.info("Chosen motor_speed=%g deg/s (frame_time=%g s, threshold=%g deg)",
                     self.motor_speed, frame_time, thr_deg)
            self.epics_pvs['RotationSpeed'].put(self.motor_speed)
            # Calculate the PSO Window step
            # Uniform mode uses min_step as the slot size; for uniform patterns min_step == 360/N,
            # so the two branches are numerically identical. For interlaced modes min_step is much
            # smaller (the tightest interlaced gap, ~360/(N*K)), which would make the window too
            # small, so 360/N is used explicitly instead.
            # All interlaced modes (1, 2, 3, ...) use 360/N: the PSO window must span
            # the full 360*K sweep, and 360/N * N*K = 360*K gives the correct window size.
            if mode == 0:
                window_step = float(min_step)
            else:
                window_step = 360.0 / float(N)
            keep_speed = True
            self.rotation_step = float(window_step)
            self.epics_pvs['PSOSlotStep'].put(self.rotation_step)

            # Create list of interlaced angles 
            interlaced_theta = None
            if mode == 0:
                delta_theta = 360.0 / N
                interlaced_theta = self.angles_uniform_multiturn_unwrapped(N=N, K=K, start_deg=self.rotation_start, delta_theta=delta_theta)
            elif mode == 1:
                interlaced_theta = self.angles_multitimbir_unwrapped(N=N, K=K, start_deg=self.rotation_start)
            elif mode == 2:
                interlaced_theta = self.angles_goldenangle_unwrapped(N=N, K=K, start_deg=self.rotation_start)
            elif mode == 3:
                interlaced_theta = self.angles_corput_unwrapped(N=N, K=K, start_deg=self.rotation_start)
            if interlaced_theta is not None:
                mode_names = {0: 'uniform', 1: 'timbir', 2: 'golden-angle', 3: 'van-der-corput'}
                log.info("InterlacedMode=%d (%s) N=%d K=%d", mode, mode_names.get(mode, 'unknown'), N, K)
                log.info("theta first10=%s", interlaced_theta[:10].tolist())
                log.info("theta around boundary=%s", interlaced_theta[N:N+10].tolist())
                log.info("theta last10=%s", interlaced_theta[-10:].tolist())

            # Program PSO and FPGA
            # compute_positions_PSO sets encoder counts, taxi positions and motor stop.
            # program_PSO4FPGA arms the PSO to send a dense coarse pulse stream.
            # program_fpga_* downselects from that stream the exact trigger angles for the chosen mode.
            self.compute_positions_PSO(
                interlaced_angles_deg=interlaced_theta,
                keep_motor_speed=keep_speed
            )

            self.cleanup_PSO()
            self.program_PSO4FPGA()

            if mode == 0:
                self.program_fpga_uniform()
            elif mode == 1:
                self.program_fpga_timbir()
            elif mode == 2:
                self.program_fpga_goldenangle()
            elif mode == 3:
                self.program_fpga_corput()
            else:
                raise ValueError(
                    f"Unknown/unsupported InterlacedMode={mode} "
                    "(0=uniform, 1=timbir, 2=golden-angle, 3=van-der-corput supported)"
                )

        # FPGA/PSO programming is done.  Now call super().begin_scan() which blocks
        # ~30s on FPFilePath.put(wait=True) / FPFileName.put(wait=True) while it
        # sets up the file writer and reads scan parameters into instance variables
        # (dark_field_mode, num_dark_fields, num_flat_fields, flat_field_mode, …).
        # super() also resets self.num_angles from the NumAngles PV (= N, not N×K),
        # so we save and restore our N×K total here.
        _num_angles_fpga = int(self.num_angles)   # N*K set by FPGA programming above
        super().begin_scan()
        self.num_angles = _num_angles_fpga         # restore N*K (super() sets N from NumAngles PV)

        # Always (re)arm HDF capture with the final total_images.
        #
        # IMPORTANT:
        #   FPNumCapture is a hard limit for the HDF plugin. If it is set too LOW,
        #   the plugin will stop writing early and you will truncate the dataset
        #   (late projections and/or end flats/darks will be missing).
        #
        # Therefore FPNumCapture should be programmed as an UPPER BOUND on the number
        # of frames that could be produced: attempted projections (self.num_angles)
        # plus all planned flats/darks.  Any "expected projections" computation below
        # is for LOGGING/DIAGNOSTICS ONLY and should not reduce FPNumCapture unless you
        # have a separate mechanism that guarantees the camera will actually drop frames.
        proj = int(self.num_angles)  # upper bound on projections (cannot exceed attempted triggers)

        if int(self.epics_pvs['TriggerSource'].get()) == 1:
            # Must be AFTER program_fpga_*() so self.pulse_indices exists/final.
            #
            # expected_proj is an estimate of how many frames the camera is likely to accept
            # at the chosen speed (taking into account deadtime). We compute it to inform the
            # user/logs, but it should not be used to reduce FPNumCapture because underestimation
            # will truncate the HDF output.
            expected_proj, info = self.expected_projections_from_fpga_indices(dt_tol_s=0.001)

            log.error("Expected projections=%d (attempted=%d) pulses/s=%.1f Tmin=%.4f",
                      expected_proj, info["attempted"], info["pulses_per_s"], info["Tmin_s"])


        self.total_images = int(proj)

        # Add planned dark/flat fields so the HDF plugin stays armed through the entire sequence
        # (begin flats/darks, projections, end flats/darks).

        if self.dark_field_mode != 'None':
            self.total_images += int(self.num_dark_fields)
        if self.dark_field_mode == 'Both':
            self.total_images += int(self.num_dark_fields)
        if self.flat_field_mode != 'None':
            self.total_images += int(self.num_flat_fields)
        if self.flat_field_mode == 'Both':
            self.total_images += int(self.num_flat_fields)

        self.epics_pvs['FPNumCapture'].put(int(self.total_images), wait=True)
        self.epics_pvs['FPCapture'].put('Capture', wait=True)
        time.sleep(1.0)   # allow NFS file creation to complete before first trigger
        self.epics_pvs['ScanStatus'].put('HDF capture armed')

        log.info("FPNumCapture RBV=%s", self.epics_pvs['FPNumCapture'].get())
        log.info("FPCapture RBV=%s", self.epics_pvs['FPCapture'].get(as_string=True))
        log.info("FPFullFileName=%s", self.epics_pvs['FPFullFileName'].get(as_string=True))

    def compute_interlaced_angles(self, mode: int, n: int):
        """
        Return (angles_deg, steps_deg).

        angles_deg: np.ndarray shape (n,)  (for mode=1 this is acquisition-order list)
        steps_deg:  np.ndarray shape (n-1,) (for mode=1 computed from monotonic/sorted angles)
        """
        if n <= 1:
            raise ValueError("Need at least 2 angles")

        start = float(self.epics_pvs['InterlacedRotationStart'].get())
        N = int(self.epics_pvs['InterlacedNumAngles'].get())
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())

        if mode == 0:
            delta_theta = 360.0 / N
            angles = self.angles_uniform_multiturn_unwrapped(N=N, K=K, start_deg=start,
                                                              delta_theta=delta_theta)
            if angles.size != n:
                raise ValueError(f"Uniform multiturn produced {angles.size} angles but expected {n}")
            steps = np.diff(angles)
            if np.any(steps <= 0):
                raise ValueError("Uniform multiturn angles must be strictly increasing.")
            return angles, steps
        elif mode == 1:
            # acquisition-order timbir angles (NOT monotonic)
            angles = self.angles_multitimbir_unwrapped(N=N, K=K, start_deg=start)
            if angles.size != n:
                raise ValueError(f"Timbir produced {angles.size} angles but expected {n}")

            # for speed/efficiency we need monotonic step sizes across the full sweep
            angles_mono = np.sort(angles)
            steps = np.diff(angles_mono)
            if np.any(steps <= 0):
                raise ValueError("Timbir monotonic angles must be strictly increasing after sort.")
            return angles, steps
        elif mode == 2:
            angles = self.angles_goldenangle_unwrapped(N=N, K=K, start_deg=start)
            if angles.size != n:
                raise ValueError(f"GoldenAngle produced {angles.size} angles but expected {n}")

            angles_mono = np.sort(angles)
            steps = np.diff(angles_mono)
            if np.any(steps <= 0):
                raise ValueError("GoldenAngle monotonic angles must be strictly increasing after sort.")
            return angles, steps

        elif mode == 3:
            angles = self.angles_corput_unwrapped(N=N, K=K, start_deg=start)
            if angles.size != n:
                raise ValueError(f"Corput produced {angles.size} angles but expected {n}")

            angles_mono = np.sort(angles)
            steps = np.diff(angles_mono)
            if np.any(steps <= 0):
                raise ValueError("Corput monotonic angles must be strictly increasing after sort.")
            return angles, steps


        else:
            raise NotImplementedError(f"InterlacedMode {mode} not implemented yet")

    def efficiency_for_speed(self, steps_deg, frame_time_s, motor_speed_deg_s):
        thr = motor_speed_deg_s * frame_time_s
        return float(np.mean(np.asarray(steps_deg) >= thr))

    def choose_speed_for_efficiency(self, steps_deg, frame_time_s, requested_efficiency):
        steps = np.sort(np.asarray(steps_deg, dtype=np.float64))
        E = max(0.0, min(1.0, float(requested_efficiency)))

        # threshold so that at least E of steps are >= threshold
        thr = float(np.quantile(steps, 1.0 - E, method="lower"))

        motor_speed = thr / float(frame_time_s)
        achieved = float(np.mean(steps >= thr))
        return motor_speed, achieved, thr

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Calls ``save_configuration()``.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.
        """
        log.info('end scan')
        # Save the configuration
        # Strip the extension from the FullFileName and add .config
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        log.info('data save location: %s', full_file_name)
        config_file_root = os.path.splitext(full_file_name)[0]
        try:
            self.save_configuration(config_file_root + '.config')
        except FileNotFoundError:
            log.error('config file write error')
            self.epics_pvs['ScanStatus'].put('Config File Write Error')

        # Put the camera back in FreeRun mode and acquiring
        self.set_trigger_mode('FreeRun', 1)

        # Set the rotation speed to maximum
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)                

        # Move the sample in (X/Y stage only).  Could be out if scan was aborted while
        # taking flat fields.  Clear self.rotation_save first so that move_sample_in()
        # does not restore the rotation to the end-of-scan angle — ReturnRotation in
        # the base end_scan() handles the final rotation position.
        self.rotation_save = None
        self.move_sample_in()

        # Reset MUX and TriggerSource to 0 so classic tomoscan_pso.py finds the hardware
        # correctly configured if the IOC is restarted with a different scan class.
        self.epics_pvs['FPGAMUX2'].put("0", wait=True)
        self.epics_pvs['TriggerSource'].put(0, wait=True)

        # Call the base class method
        super().end_scan()

    def collect_projections(self):
        """Collects projections in fly scan mode.

        This does the following:

        - Call the superclass collect_projections() function

        - Taxi to the start position

        - Set the trigger mode on the camera
   
        - Move the stage to the end position

        - Computes and sets the speed of the rotation motor so that it reaches the next projection
          angle just after the current exposure and readout are complete.

        - These will be used by the PSO to calculate the Taxi distance and rotary stage acceleration.

        - Starts the file plugin capturing in stream mode.

        - Starts the camera acquiring in external trigger mode.

        - Starts the PSOfly.

        - Wait on the PSO done.
        """
        log.info('collect projections')
        
        if self.num_angles==0:
            return
        super().collect_projections()

        log.info('taxi before starting capture')
        # Taxi before starting capture
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOStartTaxi'].get(), wait=True)

        self.set_trigger_mode('PSOExternal', self.num_angles)

        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Need to wait a short time for AcquireBusy to change to 1
        time.sleep(0.5)
        log.info('start fly scan')

        if self.epics_pvs['TriggerSource'].get() == 1:
            self.fpga_reset_and_enable(settle_s=0.05)
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOEndTaxi'].get())

        # Wait for camera with stall detection: once the motor should have stopped
        # (elapsed > motion_time) exit early if no new frame arrives for 3 s.
        # This avoids a long hang when frames are dropped (camera stays "Acquiring"
        # waiting for triggers that will never come after the motor stops).
        start = float(self.epics_pvs['PSOStartTaxi'].get())
        end   = float(self.epics_pvs['PSOEndTaxi'].get())
        motion_time = abs(end - start) / float(self.motor_speed)
        timeout     = motion_time + 30.0   # hard safety cap (was 120 s)
        stall_s     = 3.0                  # seconds without a new frame after motion done

        t0              = time.time()
        last_count      = -1
        last_frame_time = t0
        while True:
            if self.epics_pvs['CamAcquireBusy'].value == 0:
                break                      # camera finished normally
            if not self.scan_is_running:
                raise ScanAbortError       # abort requested
            elapsed = time.time() - t0
            if elapsed >= timeout:
                raise CameraTimeoutError()
            cur_count = self.epics_pvs['CamNumImagesCounter'].value
            if cur_count != last_count:
                last_count      = cur_count
                last_frame_time = time.time()
            elif elapsed > motion_time and (time.time() - last_frame_time) >= stall_s:
                log.warning('Fly scan stalled at %d/%d frames after motor stop — stopping camera',
                            cur_count, self.num_angles)
                self.epics_pvs['CamAcquire'].put('Done')
                time.sleep(0.5)
                break
            time.sleep(0.2)
            self.update_status(t0)

    def program_PSO(self):
        '''Performs programming of PSO output on the Aerotech driver.
        '''
        self.epics_pvs['ScanStatus'].put('Programming PSO')
        overall_sense, user_direction = self._compute_senses()
        log.info(f'Overall sense = {overall_sense}')
        log.info(f'User direction = {user_direction}')
        pso_command = self.epics_pvs['PSOCommand.BOUT']
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        pso_input = int(self.epics_pvs['PSOEncoderInput'].get(as_string=True))

        # Place the motor at the position where the first PSO pulse should be triggered
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        self.epics_pvs['Rotation'].put(self.rotation_start_new, wait=True, timeout=600)
        self.epics_pvs['RotationSpeed'].put(self.motor_speed)

        # Make sure the PSO control is off
        pso_command.put('PSOCONTROL %s RESET' % pso_axis, wait=True, timeout=10.0)
        # Set the output to occur from the I/O terminal on the controller
        if (pso_model == 'Ensemble'):
            pso_command.put('PSOOUTPUT %s CONTROL 1' % pso_axis, wait=True, timeout=10.0)
        elif (pso_model == 'A3200'):
            pso_command.put('PSOOUTPUT %s CONTROL 0 1' % pso_axis, wait=True, timeout=10.0)
        # Set the pulse width.  The total width and active width are the same, since this is a single pulse.
        pulse_width = self.epics_pvs['PSOPulseWidth'].get()
        pso_command.put('PSOPULSE %s TIME %f,%f' % (pso_axis, pulse_width, pulse_width), wait=True, timeout=10.0)
        # Set the pulses to only occur in a specific window
        pso_command.put('PSOOUTPUT %s PULSE WINDOW MASK' % pso_axis, wait=True, timeout=10.0)
        # Set which encoder we will use.  3 = the MXH (encoder multiplier) input, which is what we generally want
        pso_command.put('PSOTRACK %s INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)
        # Set the distance between pulses. Do this in encoder counts.
        pso_command.put('PSODISTANCE %s FIXED %d' % (pso_axis, 
                        int(np.abs(self.epics_pvs['PSOEncoderCountsPerStep'].get()))) , wait=True, timeout=10.0)
        # Which encoder is being used to calculate whether we are in the window.  1 for single axis
        pso_command.put('PSOWINDOW %s 1 INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)

        # Calculate window function parameters.  Must be in encoder counts, and is 
        # referenced from the stage location where we arm the PSO.  We are at that point now.
        # We want pulses to start at start - delta/2, end at end + delta/2.  
        range_start = -round(np.abs(self.epics_pvs['PSOEncoderCountsPerStep'].get())/ 2) * overall_sense
        range_length = np.abs(self.epics_pvs['PSOEncoderCountsPerStep'].get()) * self.num_angles
        # The start of the PSO window must be < end.  Handle this.
        if overall_sense > 0:
            window_start = range_start
            window_end = window_start + range_length
        else:
            window_end = range_start
            window_start = window_end - range_length
        pso_command.put('PSOWINDOW %s 1 RANGE %d,%d' % (pso_axis, window_start-5, window_end+5), wait=True, timeout=10.0)
        # Arm the PSO
        pso_command.put('PSOCONTROL %s ARM' % pso_axis, wait=True, timeout=10.0)


    def program_PSO4FPGA(self):
        """
        Program Aerotech PSO for FPGA downselect.

        This function ONLY configures/arms PSO. It does NOT program the FPGA.
        Note: the original “dense pass-through” mode (PSODISTANCE FIXED 1) is too 
        sensitive to noise at rest on this system and can self-trigger by picking 
        up encoder/servo noise while the stage is stationary; testing showed stable 
        behavior only for PSODISTANCE FIXED ≥ 3 (we use FIXED 33 for ~0.001° pulse spacing).

        """
        self.epics_pvs['ScanStatus'].put('Programming PSO for FPGA (coarse stream)')

        overall_sense, user_direction = self._compute_senses()
        log.info('Overall sense = %s', overall_sense)
        log.info('User direction = %s', user_direction)

        pso_command = self.epics_pvs['PSOCommand.BOUT']
        pso_model   = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        pso_axis    = self.epics_pvs['PSOAxisName'].get(as_string=True)
        pso_input   = int(self.epics_pvs['PSOEncoderInput'].get(as_string=True))

        # Use a PSO spacing that does not self-trigger at rest (FIXED 1/2 did; 3 stopped; 33 ~0.001 deg)
        pso_distance = 33  # make this a PV later if desired

        # Move to arming reference position
        self.epics_pvs['ScanStatus'].put('Returning to start position')
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        self.epics_pvs['Rotation'].put(self.rotation_start_new, wait=True, timeout=600)
        self.epics_pvs['ScanStatus'].put('Programming PSO for FPGA (coarse stream)')
        self.epics_pvs['RotationSpeed'].put(self.motor_speed)

        # Reset PSO
        pso_command.put(f'PSOCONTROL {pso_axis} RESET', wait=True, timeout=10.0)

        # Output routing
        if pso_model == 'Ensemble':
            pso_command.put(f'PSOOUTPUT {pso_axis} CONTROL 1', wait=True, timeout=10.0)
        elif pso_model == 'A3200':
            pso_command.put(f'PSOOUTPUT {pso_axis} CONTROL 0 1', wait=True, timeout=10.0)

        # Pulse width (microseconds)
        pulse_width = self.epics_pvs['PSOPulseWidth'].get()
        pso_command.put(f'PSOPULSE {pso_axis} TIME {pulse_width},{pulse_width}', wait=True, timeout=10.0)

        # Gate by window
        pso_command.put(f'PSOOUTPUT {pso_axis} PULSE WINDOW MASK', wait=True, timeout=10.0)

        # Tracking encoder
        pso_command.put(f'PSOTRACK {pso_axis} INPUT {pso_input}', wait=True, timeout=10.0)

        # Coarse PSO stream for FPGA downselect
        pso_command.put(f'PSODISTANCE {pso_axis} FIXED {int(pso_distance)}', wait=True, timeout=10.0)

        # Window encoder
        pso_command.put(f'PSOWINDOW {pso_axis} 1 INPUT {pso_input}', wait=True, timeout=10.0)

        # Window range (same as existing logic)
        counts_per_step = abs(float(self.epics_pvs['PSOEncoderCountsPerStep'].get()))
        range_start  = -round(counts_per_step / 2) * overall_sense
        range_length = counts_per_step * self.num_angles

        if overall_sense > 0:
            window_start = range_start
            window_end   = window_start + range_length
        else:
            window_end   = range_start
            window_start = window_end - range_length

        pso_command.put(
            f'PSOWINDOW {pso_axis} 1 RANGE {int(window_start-5)},{int(window_end+5)}',
            wait=True,
            timeout=10.0
        )

        # --- Arm PSO ---
        pso_command.put(f'PSOCONTROL {pso_axis} ARM', wait=True, timeout=10.0)

        # Store for FPGA routines (so they use the same distance)
        self.pso_distance_fpga = int(pso_distance)
        self.pso_window_counts_fpga = int(round(abs(window_end - window_start)))

    def program_fpga_uniform(self):
        """
        Program FPGA for uniform downselect.

        Assumes:
          - program_PSO4FPGA() already ran and set:
              self.pso_distance_fpga
              self.pso_window_counts_fpga
          - FPGA uses PSO pulses as its input clock (indices are PSO-pulse indices).
        """
        self.epics_pvs['ScanStatus'].put('Programming FPGA (uniform multiturn)')

        pso_distance = int(getattr(self, "pso_distance_fpga", 33))
        window_counts = int(getattr(self, "pso_window_counts_fpga", 0))
        if window_counts <= 0:
            raise ValueError("pso_window_counts_fpga not set. Call program_PSO4FPGA() first.")

        total_pso_pulses = window_counts // pso_distance

        N = int(self.epics_pvs['InterlacedNumAngles'].get())
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())
        n = N * K

        if total_pso_pulses <= n:
            raise ValueError(f"total_pso_pulses ({total_pso_pulses}) must be > n_triggers ({n})")

        start_deg   = float(self.epics_pvs['InterlacedRotationStart'].get())
        delta_theta = 360.0 / N

        # Acquisition-order angles with per-rotation fractional offset
        angles_deg = self.angles_uniform_multiturn_unwrapped(N=N, K=K, start_deg=start_deg,
                                                              delta_theta=delta_theta)
        if angles_deg.size != n:
            raise ValueError(f"Uniform multiturn angle list length mismatch: expected {n}, got {angles_deg.size}")

        # Map degrees -> encoder counts -> PSO pulse index
        counts_per_deg = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.0
        rel_counts = np.round((angles_deg - start_deg) * counts_per_deg).astype(np.int64)
        pulse_idx  = (rel_counts // pso_distance).astype(np.int64)

        if pulse_idx.min() < 0 or pulse_idx.max() >= total_pso_pulses:
            raise ValueError(
                "Uniform multiturn triggers fall outside the PSO window. "
                "Check PSOCountsPerRotation and PSO window sizing."
            )

        # Enforce strictly increasing
        for i in range(1, n):
            if pulse_idx[i] <= pulse_idx[i - 1]:
                pulse_idx[i] = pulse_idx[i - 1] + 1

        if pulse_idx[-1] >= total_pso_pulses:
            raise ValueError(
                "Not enough PSO pulses in window to realize uniform multiturn after quantization fixes."
            )

        self.pulse_indices = pulse_idx.tolist()

        log.info("program_fpga_uniform:")
        log.info("  N=%d K=%d n=%d delta_theta=%g deg", N, K, n, delta_theta)
        log.info("  pso_distance=%d counts/PSO-pulse, total_pso_pulses=%d", pso_distance, total_pso_pulses)
        log.info("  first 10 indices=%s", self.pulse_indices[:10])
        log.info("  last 10 indices=%s", self.pulse_indices[-10:])

        self.write_PSO_array()

    def cleanup_PSO(self):
        '''Cleanup activities after a PSO scan. 
        Turns off PSO and sets the speed back to default.
        '''
        log.info('Cleaning up PSO programming.')
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        pso_command = self.epics_pvs['PSOCommand.BOUT']
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        if (pso_model == 'Ensemble'):
            pso_command.put('PSOWINDOW %s OFF' % pso_axis, wait=True)
        elif (pso_model == 'A3200'):
            pso_command.put('PSOWINDOW %s 1 OFF' % pso_axis, wait=True)
        pso_command.put('PSOCONTROL %s OFF' % pso_axis, wait=True)

    def _compute_senses(self):
        '''Computes whether this motion will be increasing or decreasing encoder counts.
        
        user direction, overall sense.
        '''
        # Encoder direction compared to dial coordinates
        encoder_dir = 1 if self.epics_pvs['PSOCountsPerRotation'].get() > 0 else -1
        # Get motor direction (dial vs. user); convert (0,1) = (pos, neg) to (1, -1)
        motor_dir = 1 if self.epics_pvs['RotationDirection'].get() == 0 else -1
        # Figure out whether motion is in positive or negative direction in user coordinates
        user_direction = 1 if self.rotation_stop > self.rotation_start else -1
        # Figure out overall sense: +1 if motion in + encoder direction, -1 otherwise
        log.debug((encoder_dir, motor_dir, user_direction))
        return user_direction * motor_dir * encoder_dir, user_direction
        
    def compute_positions_PSO(self, interlaced_angles_deg=None, keep_motor_speed=False):
        overall_sense, user_direction = self._compute_senses()


        # Use self.rotation_step as the "safety step" for encoder/taxi/window math
        encoder_multiply = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.
        raw_delta_encoder_counts = self.rotation_step * encoder_multiply
        delta_encoder_counts = round(raw_delta_encoder_counts)
        if abs(raw_delta_encoder_counts - delta_encoder_counts) > 1e-4:
            log.warning('  *** *** *** Requested scan would have used a non-integer number of encoder counts.')
            log.warning('  *** *** *** Calculated # of encoder counts per step = {0:9.4f}'.format(raw_delta_encoder_counts))
            log.warning('  *** *** *** Instead, using {0:d}'.format(delta_encoder_counts))
        self.epics_pvs['PSOEncoderCountsPerStep'].put(delta_encoder_counts)

        # Update step to the quantized value (still used for taxi/window)
        self.rotation_step = delta_encoder_counts / encoder_multiply
        self.epics_pvs['RotationStep'].put(self.rotation_step)

        # Frame time
        time_per_angle = self.compute_frame_time()
        # Only compute motor_speed from rotation_step for classic uniform scans
        if not keep_motor_speed:
            self.motor_speed = np.abs(self.rotation_step) / time_per_angle

        # accel/taxi logic unchanged
        motor_accl_time = float(self.epics_pvs['RotationAccelTime'].get())
        accel_dist = motor_accl_time / 2.0 * float(self.motor_speed)

        if overall_sense > 0:
            self.rotation_start_new = self.rotation_start
        else:
            self.rotation_start_new = self.rotation_start - (2 - self.readout_margin) * self.rotation_step

        if self.rotation_step > 0:
            taxi_dist = math.ceil(accel_dist / self.rotation_step + 0.5) * self.rotation_step
        else:
            taxi_dist = math.floor(accel_dist / self.rotation_step - 0.5) * self.rotation_step

        self.epics_pvs['PSOStartTaxi'].put(self.rotation_start_new - taxi_dist * user_direction)

        self.rotation_stop = (self.rotation_start_new + (self.num_angles - 1) * self.rotation_step)
        self.epics_pvs['PSOEndTaxi'].put(self.rotation_stop + taxi_dist * user_direction)

        # Theta: uniform for classic, otherwise use provided interlaced list
        if interlaced_angles_deg is None:
            self.theta = self.rotation_start + np.arange(self.num_angles) * self.rotation_step
        else:
            self.theta = np.asarray(interlaced_angles_deg, dtype=np.float32)

    def writeRAM_memPulseSeq(self):
        # note: BRAM ena signal (memPulseSeq_ENA) always 1.

        self.epics_pvs['FPGAWrt'].put("1")
        time.sleep(.001)

        for i in range(len(self.delays)):
            self.epics_pvs['FPGAAddr'].put(i, wait=True, timeout=1000000.0)
            self.epics_pvs['FPGADin'].put(self.delays[i], wait=True, timeout=1000000.0)
            time.sleep(.001)
            self.epics_pvs['FPGAClk'].put("1!", wait=True, timeout=1000000.0)
            time.sleep(.001)

        self.epics_pvs['FPGAWrt'].put("0")

        n_trig = int(len(self.delays))
        self.epics_pvs['FPGANSignal'].put(n_trig, wait=True, timeout=1000000.0)

        # log what we actually programmed
        log.info("FPGA programmed: n_triggers=%d (FPGANSignal RBV=%s)",
                 n_trig, self.epics_pvs['FPGANSignal'].get())


    def positions_to_delays(self):
        """
        Convert an array of trigger positions into delays between pulses.

        positions: list or array of trigger indices (0-based, increasing)
                   Example: [0, 3, 5]

        Returns a list of delays. Example: [0, 2, 1]
        """
        if not self.pulse_indices:
            return []

        self.delays = [self.pulse_indices[0]] # pulses before first trigger

        for i in range(len(self.pulse_indices) - 1):
            delay = self.pulse_indices[i+1] - self.pulse_indices[i] - 1
            if delay < 0:
                raise ValueError("Trigger positions must be strictly increasing.")
            self.delays.append(delay)

        return self.delays

    def write_PSO_array(self):
        delays = self.positions_to_delays()
        self.writeRAM_memPulseSeq()

    def fpga_reset_and_enable(self, settle_s=0.05):
        """Reset FPGA counters and enable trigger using the known-good sequence."""
        reset_pv  = self.epics_pvs['BUFFER-1_IN_Signal']
        enable_pv = self.epics_pvs['BUFFER-2_IN_Signal']

        # reset: 0 -> 1!
        reset_pv.put("0", wait=True)
        time.sleep(settle_s)
        reset_pv.put("1!", wait=True)
        time.sleep(settle_s)

        # enable: 0 -> 1
        enable_pv.put("0", wait=True)
        time.sleep(settle_s)
        enable_pv.put("1", wait=True)
        time.sleep(settle_s)

        log.info("FPGA reset/enable RBV: reset=%s enable=%s",
                 reset_pv.get(as_string=True),
                 enable_pv.get(as_string=True))


    def _bit_reverse(self, n: int, bits: int) -> int:
        return int(f"{n:0{bits}b}"[::-1], 2)

    def _ensure_power_of_two(self, k: int):
        if k <= 0 or (k & (k - 1)) != 0:
            raise ValueError("InterlacedNumberOfRotation (K) must be a power of 2")

    def angles_uniform_multiturn_unwrapped(self, N: int, K: int, start_deg: float = 0.0,
                                            delta_theta: float = None) -> np.ndarray:
        """Uniform multi-turn angles with per-rotation fractional offset.

        Each rotation k contributes N angles shifted by k/K * delta_theta from
        the base uniform grid and by 360*k degrees (multi-turn motor position).
        After K rotations the sorted angles fill [start_deg, start_deg+360) at
        spacing delta_theta/K.

        Parameters
        ----------
        N : int            Number of angles per rotation.
        K : int            Number of rotations.
        start_deg : float  Starting angle in degrees.
        delta_theta : float, optional
            Angular step size. If None, computed from
            (InterlacedRotationStop - InterlacedRotationStart) / N.

        Returns
        -------
        np.ndarray, shape (N*K,)
            Acquisition-order unwrapped angles (rotation 0 block, rotation 1, ...).
        """
        if delta_theta is None:
            delta_theta = 360.0 / N
        n = np.arange(N, dtype=np.float64)
        blocks = [start_deg + (n + k / K) * delta_theta + 360.0 * k for k in range(K)]
        return np.concatenate(blocks).astype(np.float64)

    def angles_multitimbir_unwrapped(self, N: int, K: int, start_deg: float = 0.0):
        """
        Multi-timbir pattern over K full rotations.

        Returns angles in degrees (unwrapped), length N*K, in acquisition order
        (rotation 0 block, then rotation 1 block, ...).

        The returned array is always monotonically increasing: each block k covers
        [start_deg + 360*k, start_deg + 360*(k+1)) with uniform spacing 360/N,
        so concatenating blocks in order yields a globally sorted sequence.
        """
        self._ensure_power_of_two(K)
        bits = int(np.log2(K))
        theta = []
        for loop_turn in range(K):
            base_turn = 360.0 * loop_turn
            subloop = self._bit_reverse(loop_turn, bits)
            for i in range(N):
                idx = i * K + subloop
                angle_deg = idx * 360.0 / (N * K)   # [0, 360)
                theta.append(start_deg + base_turn + angle_deg)

        return np.asarray(theta, dtype=np.float64)


    # --- 3) Correct program_fpga_timbir(): preserve N*K triggers, no sort/unique ---

    def program_fpga_timbir(self):
        """
        Program FPGA downselect table for Timbir (multi-rotation interlaced).

        Assumes:
          - Continuous sweep 0 -> 360K (unwrapped)
          - N triggers per rotation over K rotations => total n = N*K
          - program_PSO4FPGA() already ran and set:
              self.pso_distance_fpga
              self.pso_window_counts_fpga
          - FPGA expects delays; we provide absolute pulse indices and convert later.
        """
        self.epics_pvs['ScanStatus'].put('Programming FPGA (Timbir)')

        pso_distance = int(getattr(self, "pso_distance_fpga", 33))
        window_counts = int(getattr(self, "pso_window_counts_fpga", 0))
        if window_counts <= 0:
            raise ValueError("pso_window_counts_fpga not set. Call program_PSO4FPGA() first.")

        total_pso_pulses = window_counts // pso_distance

        N = int(self.epics_pvs['InterlacedNumAngles'].get())
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())
        n = N * K

        if total_pso_pulses <= n:
            raise ValueError(f"total_pso_pulses ({total_pso_pulses}) must be > n_triggers ({n})")

        start_deg = float(self.epics_pvs['InterlacedRotationStart'].get())

        # 1) Timbir acquisition-order angles (do NOT sort)
        angles_deg = self.angles_multitimbir_unwrapped(N=N, K=K, start_deg=start_deg)

        if angles_deg.size != n:
            raise ValueError(f"Timbir angle list length mismatch: expected {n}, got {angles_deg.size}")

        # 2) Map degrees -> encoder counts -> PSO pulse index
        counts_per_deg = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.0
        rel_counts = np.round((angles_deg - start_deg) * counts_per_deg).astype(np.int64)
        pulse_idx = (rel_counts // pso_distance).astype(np.int64)

        # Prefer fail-fast instead of clip (clip would silently corrupt the pattern)
        if pulse_idx.min() < 0 or pulse_idx.max() >= total_pso_pulses:
            raise ValueError(
                "Timbir triggers fall outside the PSO window. "
                "PSO window sizing is inconsistent with PSOCountsPerRotation / start_deg."
            )

        # 3) Enforce strictly increasing WITHOUT dropping triggers (no unique)
        for i in range(1, n):
            if pulse_idx[i] <= pulse_idx[i - 1]:
                pulse_idx[i] = pulse_idx[i - 1] + 1

        if pulse_idx[-1] >= total_pso_pulses:
            raise ValueError(
                "Not enough PSO pulses in window to realize Timbir after quantization/collision fixes. "
                "Increase PSO pulse density (smaller pso_distance) or enlarge PSO window."
            )

        self.pulse_indices = pulse_idx.tolist()

        log.info("program_fpga_timbir:")
        log.info("  N=%d K=%d n=%d", N, K, n)
        log.info("  pso_distance=%d counts/PSO-pulse, total_pso_pulses=%d", pso_distance, total_pso_pulses)
        log.info("  first 10 indices=%s", self.pulse_indices[:10])
        log.info("  last 10 indices=%s", self.pulse_indices[-10:])

        self.write_PSO_array()

    def angles_goldenangle_unwrapped(self, N: int, K: int, start_deg: float = 0.0):
        """
        Golden-angle interlaced pattern over K rotations.

        Returns unwrapped angles (deg), length N*K, in acquisition order
        (rotation 0 block, then rotation 1 block, ...).

        The returned array is always monotonically increasing: each block k is sorted
        within [0°, 360°) and then shifted by start_deg + 360°*k, so concatenating
        blocks in order yields a globally sorted sequence.
        """
        if N <= 0 or K <= 0:
            raise ValueError("N and K must be > 0")

        golden_angle = 360.0 * (3.0 - np.sqrt(5.0)) / 2.0
        phi_inv = (np.sqrt(5.0) - 1.0) / 2.0

        # base angles for rotation 0, sorted within [0,360)
        base = np.array([(start_deg + i * golden_angle) % 360.0 for i in range(N)], dtype=np.float64)
        base.sort()

        theta = []
        for k in range(K):
            if k == 0:
                block = base
            else:
                offset = (k / (N + 1.0)) * 360.0 * phi_inv
                block = np.sort((base + offset) % 360.0)

            # unwrap: shift block into [start_deg + 360*k, start_deg + 360*(k+1))
            theta.extend((start_deg + 360.0 * k + block).tolist())

        return np.asarray(theta, dtype=np.float64)

    def program_fpga_goldenangle(self):
        """
        Program FPGA downselect table for Golden-Angle interlaced acquisition.

        Assumes:
          - Continuous sweep 0 -> 360K (unwrapped)
          - N triggers per rotation over K rotations => total n = N*K
          - program_PSO4FPGA() already ran and set pso_distance_fpga, pso_window_counts_fpga
        """
        self.epics_pvs['ScanStatus'].put('Programming FPGA (GoldenAngle)')

        pso_distance  = int(getattr(self, "pso_distance_fpga", 33))
        window_counts = int(getattr(self, "pso_window_counts_fpga", 0))
        if window_counts <= 0:
            raise ValueError("pso_window_counts_fpga not set. Call program_PSO4FPGA() first.")

        total_pso_pulses = window_counts // pso_distance

        N = int(self.epics_pvs['InterlacedNumAngles'].get())
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())
        n = N * K

        if total_pso_pulses <= n:
            raise ValueError(f"total_pso_pulses ({total_pso_pulses}) must be > n_triggers ({n})")

        start_deg = float(self.epics_pvs['InterlacedRotationStart'].get())

        # Acquisition-order golden-angle unwrapped list
        angles_deg = self.angles_goldenangle_unwrapped(N=N, K=K, start_deg=start_deg)
        if angles_deg.size != n:
            raise ValueError(f"GoldenAngle angle list length mismatch: expected {n}, got {angles_deg.size}")

        # Map degrees -> encoder counts -> PSO pulse index
        counts_per_deg = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.0
        rel_counts = np.round((angles_deg - start_deg) * counts_per_deg).astype(np.int64)
        pulse_idx = (rel_counts // pso_distance).astype(np.int64)

        # Prefer fail-fast instead of clip
        if pulse_idx.min() < 0 or pulse_idx.max() >= total_pso_pulses:
            raise ValueError(
                "GoldenAngle triggers fall outside the PSO window. "
                "PSO window sizing is inconsistent with PSOCountsPerRotation / start_deg."
            )

        # Enforce strictly increasing without dropping triggers
        for i in range(1, n):
            if pulse_idx[i] <= pulse_idx[i - 1]:
                pulse_idx[i] = pulse_idx[i - 1] + 1

        if pulse_idx[-1] >= total_pso_pulses:
            raise ValueError(
                "Not enough PSO pulses in window to realize GoldenAngle after quantization/collision fixes. "
                "Increase PSO pulse density (smaller pso_distance) or enlarge PSO window."
            )

        self.pulse_indices = pulse_idx.tolist()

        log.info("program_fpga_goldenangle:")
        log.info("  N=%d K=%d n=%d", N, K, n)
        log.info("  pso_distance=%d counts/PSO-pulse, total_pso_pulses=%d", pso_distance, total_pso_pulses)
        log.info("  first 10 indices=%s", self.pulse_indices[:10])
        log.info("  last 10 indices=%s", self.pulse_indices[-10:])

        self.write_PSO_array()

    def expected_projections_from_fpga_indices(self, frame_time_s=None, dt_tol_s=0.001):
        """
        Predict accepted projections by comparing FPGA trigger separations in TIME
        against Tmin (compute_frame_time(), which already includes margin), but with a
        small tolerance dt_tol_s.

        dt_tol_s relaxes the acceptance threshold to: Tmin_eff = Tmin - dt_tol_s
        """
        pulse_indices = getattr(self, "pulse_indices", None)
        if not pulse_indices:
            return 0, {"reason": "no pulse_indices"}

        Tmin = float(self.compute_frame_time() if frame_time_s is None else frame_time_s)
        if Tmin <= 0:
            raise ValueError(f"Invalid Tmin={Tmin}")

        dt_tol_s = float(dt_tol_s)
        Tmin_eff = max(0.0, Tmin - dt_tol_s)

        counts_per_deg = float(self.epics_pvs["PSOCountsPerRotation"].get()) / 360.0
        v_deg_s = abs(float(self.motor_speed))
        if v_deg_s <= 0:
            raise ValueError(f"Invalid motor_speed={self.motor_speed}")

        pso_distance = int(getattr(self, "pso_distance_fpga", 33))
        if pso_distance <= 0:
            raise ValueError(f"Invalid pso_distance={pso_distance}")

        pulses_per_s = (v_deg_s * counts_per_deg) / float(pso_distance)
        if pulses_per_s <= 0:
            raise ValueError(f"Invalid pulses_per_s={pulses_per_s}")

        accepted = 1
        last = int(pulse_indices[0])

        for idx in pulse_indices[1:]:
            idx = int(idx)
            dt = (idx - last) / pulses_per_s
            if dt >= Tmin_eff:
                accepted += 1
                last = idx

        attempted = int(len(pulse_indices))
        expected = int(min(accepted, attempted, int(getattr(self, "num_angles", attempted))))

        info = {
            "Tmin_s": Tmin,
            "Tmin_eff_s": Tmin_eff,
            "dt_tol_s": dt_tol_s,
            "pulses_per_s": float(pulses_per_s),
            "attempted": attempted,
            "accepted_raw": int(accepted),
            "expected_proj": expected,
        }
        return expected, info



    def angles_corput_unwrapped(self, N: int, K: int, start_deg: float = 0.0) -> np.ndarray:
        """
        Van der Corput interlaced pattern over K rotations, returned as a MONOTONIC
        unwrapped list suitable for a single continuous fly scan.

        Returns
        -------
        theta : np.ndarray, shape (N*K,)
            Strictly increasing unwrapped angles in degrees spanning approximately
            [start_deg, start_deg + 360*K).

        Notes
        -----
        This generator is consistent with other interlaced fly-scan modes in that it
        produces a monotonic rotation trigger set. A true bit-reversed acquisition
        order would require non-monotonic motion and is not compatible with fly scans.
        """
        N = int(N)
        K = int(K)
        start = float(start_deg)

        if N <= 0 or K <= 0:
            raise ValueError("N and K must be > 0")

        # Nominal per-rotation step (deg)
        delta_theta = 360.0 / float(N)

        # --- bit-reversed rotation order (length K) ---
        bitsK = int(np.ceil(np.log2(K)))
        MK = 1 << bitsK
        p_corput = np.array([self._bit_reverse(i, bitsK) for i in range(MK)], dtype=np.int64)
        p_corput = p_corput[p_corput < K]
        if len(p_corput) != K:
            raise ValueError(f"Corput p_corput length mismatch: expected {K}, got {len(p_corput)}")

        offsets = (p_corput.astype(np.float64) / float(K)) * delta_theta

        # --- bit-reversed intra-rotation index order (length N) ---
        bitsN = int(np.ceil(np.log2(N)))
        MN = 1 << bitsN
        indices = np.array([self._bit_reverse(i, bitsN) for i in range(MN)], dtype=np.int64)
        indices = indices[indices < N]
        if len(indices) != N:
            raise ValueError(f"Corput indices length mismatch: expected {N}, got {len(indices)}")

        base = start + np.arange(N, dtype=np.float64) * delta_theta

        # Build the full unwrapped set (may be non-monotonic in construction)
        blocks = []
        for k in range(K):
            loop_angles = base[indices] + offsets[k]
            loop_angles_mod = np.mod(loop_angles - start, 360.0) + start
            loop_angles_unwrapped = loop_angles_mod + 360.0 * k
            blocks.append(loop_angles_unwrapped)

        theta = np.concatenate(blocks).astype(np.float64)

        # Critical for fly scans: enforce monotonic order in time
        theta = np.sort(theta)

        # Sanity: should be strictly increasing (if not, you have quantization duplicates)
        if np.any(np.diff(theta) <= 0):
            raise ValueError("Corput theta is not strictly increasing after sort (unexpected).")

        return theta


    def program_fpga_corput(self):
        """
        Program FPGA downselect table for Van der Corput interlaced acquisition.
        """
        self.epics_pvs['ScanStatus'].put('Programming FPGA (VanDerCorput)')

        pso_distance  = int(getattr(self, "pso_distance_fpga", 33))
        window_counts = int(getattr(self, "pso_window_counts_fpga", 0))
        if window_counts <= 0:
            raise ValueError("pso_window_counts_fpga not set. Call program_PSO4FPGA() first.")

        total_pso_pulses = window_counts // pso_distance

        N = int(self.epics_pvs['InterlacedNumAngles'].get())
        K = int(self.epics_pvs['InterlacedNumberOfRotation'].get())
        n = N * K

        if total_pso_pulses <= n:
            raise ValueError(f"total_pso_pulses ({total_pso_pulses}) must be > n_triggers ({n})")

        start_deg = float(self.epics_pvs['InterlacedRotationStart'].get())

        # Acquisition-order Corput unwrapped list
        angles_deg = self.angles_corput_unwrapped(N=N, K=K, start_deg=start_deg)
        if angles_deg.size != n:
            raise ValueError(f"Corput angle list length mismatch: expected {n}, got {angles_deg.size}")

        # Map degrees -> encoder counts -> PSO pulse index
        counts_per_deg = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.0
        rel_counts = np.round((angles_deg - start_deg) * counts_per_deg).astype(np.int64)
        pulse_idx = (rel_counts // pso_distance).astype(np.int64)

        if pulse_idx.min() < 0 or pulse_idx.max() >= total_pso_pulses:
            raise ValueError(
                "Corput triggers fall outside the PSO window. "
                "PSO window sizing is inconsistent with PSOCountsPerRotation / start_deg."
            )

        # Enforce strictly increasing without dropping triggers
        for i in range(1, n):
            if pulse_idx[i] <= pulse_idx[i - 1]:
                pulse_idx[i] = pulse_idx[i - 1] + 1

        if pulse_idx[-1] >= total_pso_pulses:
            raise ValueError(
                "Not enough PSO pulses in window to realize Corput after quantization/collision fixes. "
                "Increase PSO pulse density (smaller pso_distance) or enlarge PSO window."
            )

        self.pulse_indices = pulse_idx.tolist()

        log.info("program_fpga_corput:")
        log.info("  N=%d K=%d n=%d", N, K, n)
        log.info("  pso_distance=%d counts/PSO-pulse, total_pso_pulses=%d", pso_distance, total_pso_pulses)
        log.info("  first 10 indices=%s", self.pulse_indices[:10])
        log.info("  last 10 indices=%s", self.pulse_indices[-10:])

        self.write_PSO_array()
