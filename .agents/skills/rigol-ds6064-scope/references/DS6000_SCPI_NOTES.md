# DS6000 / DS6064 SCPI Notes

## Common Safe Commands

```text
*IDN?                         Query instrument identity
:RUN                          Start acquisition
:STOP                         Stop acquisition
:SINGle                       Single acquisition
:AUToscale                    Autoscale, changes display setup
:MEASure:ITEM? VPP,CHANnel1   Measure peak-to-peak voltage on CH1
:MEASure:ITEM? FREQuency,CHANnel1
:MEASure:ITEM? PERiod,CHANnel1
:MEASure:ITEM? PDUTy,CHANnel1
:WAVeform:SOURce CHANnel1     Set waveform source
:WAVeform:FORMat ASCii        Set waveform data format to ASCII
:WAVeform:DATA?               Query waveform data
```

## USB-TMC Resource

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

## Blocked By Default

```text
*RST
:STORage
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```
