# src/gas_sensing_app/hardware/keithley_2400.py

from pymeasure.instruments.keithley import keithley2400 as K2400
import time

class Keithley2400:
    def __init__(self, resource_string):
        # Stablish the connection  
        self.inst = K2400(
            resource_string,
            timeout=5000, 
            baud_rate=9600
        )
        
        # Initial Reset and Clear
        self.inst.reset() # *RST
        self.inst.clear() # *CLS
        print(f"Keithley 2400 connected at {resource_string}.")
        time.sleep(0.5)


    def setup_resistance(self, auto_range=True, manual_range=None, four_wire=False, nplc=1):
        """Configure the device for resistance measurement."""
        sense_str = "4-Wire (Remote)" if four_wire else "2-Wire (Local)"
        print(f"Configuring Keithley for Resistance ({sense_str}, Auto-Range: {auto_range})...")
        
        # Clear any existing data in the buffer
        #   # TODO check whether this is necessary as there are no buffered measurements coded
        self.inst.write(":TRAC:CLEAR")
        
        if four_wire: 
            # Remote Sense On (4-wire)
            self.inst.wires = 4 # :SYST:RSEN ON
        else:  
            # Remote Sense Off (2-wire)
            self.inst.wires = 2 # :SYST:RSEN OFF

        self.inst.resistance_mode_auto_enabled = auto_range # :SENS:RES:RANG:AUTO {ON | OFF}
        self.inst.resistance_nplc = nplc # :SENS:RES:NPLCYCLES {nplc}
        
        if manual_range is not None:
            # By providing a manual_range resistance_range_auto_enabled is implicitly set to False
            self.inst.resistance_range = manual_range # :SENS:RES:RANG {manual_range}
            
            if auto_range == True:
                print("Info: Manual range selected. Auto range will be ignored.")    

        self.inst.enable_source() # :OUTPUT ON
    
    def get_reading(self):
        """Call this inside your 1s loop. No setup, just data."""
        try:
            self.inst.resistance # :MEASURE:RESISTANCE?
        except Exception as e:
            return f"Error: {e}"
    
    def close(self):
        self.inst.shutdown() # :OUTPUT OFF

# --- The Master Loop (Your 1s Data Acquisition) ---
if __name__ == "__main__":
    PORT = "ASRL/dev/cu.usbserial-120::INSTR"
    sensor = Keithley2400(PORT)
    
    # SETUP ONCE
    sensor.setup_resistance()
    
    print("\nStarting 1s logging loop. Press Ctrl+C to stop.\n")
    try:
        while True:
            start_time = time.time()
            
            value = sensor.get_reading()
            print(f"[{time.strftime('%H:%M:%S')}] Resistance: {value:.4e} Ohms")
            
            # Precise 1s timing (compensating for command execution time)
            elapsed = time.time() - start_time
            time.sleep(max(0, 1.0 - elapsed))
            
    except KeyboardInterrupt:
        print("\nStopping experiment...")
        
    finally:
        sensor.close()