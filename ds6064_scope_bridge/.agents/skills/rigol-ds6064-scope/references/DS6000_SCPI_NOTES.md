# DS6000 / DS6064 SCPI Notes

## Common Safe Commands

```text
*IDN?                         Query instrument identity
:RUN                          Start acquisition
:STOP                         Stop acquisition
:SINGle                       Single acquisition
:AUToscale                    Autoscale, changes display setup
:MEASure:VPP? CHANnel1       Measure peak-to-peak voltage on CH1
:MEASure:FREQuency? CHANnel1 Measure frequency on CH1
:MEASure:PERiod? CHANnel1    Measure period on CH1
:MEASure:PDUTy? CHANnel1     Measure positive duty cycle on CH1
:WAVeform:SOURce CHANnel1     Set waveform source
:WAVeform:FORMat BYTE         Set waveform data format to byte samples
:WAVeform:DATA?               Query waveform data
```

The DS6000 programming guide documents `:WAVeform:FORMat` as `{WORD|BYTE}`. Do not use `ASCii` for this model.

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
