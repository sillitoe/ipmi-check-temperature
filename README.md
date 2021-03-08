# ipmi-check-temperature

Simple script that uses `ipmitool` to check room temperature (based on "Inlet Temp"); sends email notification if the temperature exceeds a maximum.

Important: there are many dedicated monitoring/reporting tools and utilities out there and this is absolutely not intended to replace any of them. 
This is here as a simple, redundant, last-resort warning if all other safety checks have failed.
