#!/usr/bin/python
"""
Simple Watchdog Timer
"""
'''
Stolen From:
--------------------------------------------------------------------------------
Module Name:    watchdog.py
Author:         Jon Peterson (PIJ)
Description:    This module implements a simple watchdog timer for Python.
--------------------------------------------------------------------------------
                      Copyright (c) 2012, Jon Peterson
--------------------------------------------------------------------------------
'''

# Imports
from time import sleep
from threading import Timer
import thread

# Watchdog Class
class Watchdog(object):
    
    def __init__(self, time=1.0):
        ''' Class constructor. The "time" argument has the units of seconds. '''
        self._time = time
        return
        
    def StartWatchdog(self):
        ''' Starts the watchdog timer. '''
        self._timer = Timer(self._time, self._WatchdogEvent)
        self._timer.daemon = True
        self._timer.start()
        return
        
    def PetWatchdog(self):
        ''' Reset watchdog timer. '''
        self.StopWatchdog()
        self.StartWatchdog()
        return
        
    def _WatchdogEvent(self):
        '''
        This internal method gets called when the timer triggers. A keyboard 
        interrupt is generated on the main thread. The watchdog timer is stopped 
        when a previous event is tripped.
        '''
        print 'Watchdog event...'
        self.StopWatchdog()
        thread.interrupt_main()
        # thread.interrupt_main()
        # thread.interrupt_main()
        return

    def StopWatchdog(self):
        ''' Stops the watchdog timer. '''
        self._timer.cancel()
        


def main():
    ''' This function is used to unit test the watchdog module. '''
    
    w = Watchdog(1.0)
    w.StartWatchdog()

    for i in range(0, 11):
        print 'Testing %d...' % i
        
        try:
            if (i % 3) == 0:
                sleep(1.5)
            else:
                sleep(0.5)
        except:
            print 'MAIN THREAD KNOWS ABOUT WATCHDOG'
                
        w.PetWatchdog()

    w.StopWatchdog()  # Not strictly necessary
    
    return

if __name__ == '__main__':
    main()

