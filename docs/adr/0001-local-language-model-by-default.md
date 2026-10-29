# Local language model by default, hosted model optional

The portal's AI runs on a local model (LM Studio serving Qwen) by default, so it works offline and portal data stays on NDMA's machines. Every AI feature reaches the model through one seam, so a deployment may switch a hosted model on for jobs where local quality falls short, such as Urdu writing or multi-step tool use. A feature must still work, perhaps less well, with the local model alone.
