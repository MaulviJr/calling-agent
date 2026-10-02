// The browser's device rate is not assumed to be 16 kHz. Average source samples
// into 16 kHz frames and send 80 ms chunks; output is silence (no microphone echo).
class AvaCapture extends AudioWorkletProcessor {
  constructor(){
    super();
    this.buffer=new Int16Array(1280);
    this.index=0;
    this.phase=0;
    this.sum=0;
    this.count=0;}

  process(inputs)
  {
    const input=inputs[0]?.[0]; 
    if(!input)return true;
    for(const sample of input){
      this.sum+=sample;this.count++;this.phase+=16000;
      if(this.phase>=sampleRate){
        this.phase-=sampleRate;
        this.buffer[this.index++]=Math.round(Math.max(-1,Math.min(1,this.sum/this.count))*32767);
        this.sum=0;this.count=0;
        if(this.index===1280){this.port.postMessage(this.buffer.buffer,[this.buffer.buffer]);this.buffer=new Int16Array(1280);this.index=0;}
      }
    }
    return true;
  }
}
registerProcessor('ava-capture',AvaCapture);
