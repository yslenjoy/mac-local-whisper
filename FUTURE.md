P0
- [ ] 直接插入外部软件（非终端）权限
- [x] 稳定性（2026-04-01）：转写移至主线程通过 queue 执行，避免 daemon thread 调用 torch/C 扩展导致 segfault 及 semaphore 泄漏
  ```
  ● 录音中...
  ● 录音中...
  ◎ 转写中...
  zsh: segmentation fault  /Library/Developer/CommandLineTools/usr/bin/python3 
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % 6
  zsh: command not found: 6
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % 
  (base) yslenjoy@vpnduopool-10-251-160-72 Downloads % No it, when I say it/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9/multiprocessing/resource_tracker.py:216: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
  ```
- [x] 标点（2026-04-01）
  - [x] 末尾不要句号
  - [x] 用中文逗号而不是英文的

P1
- [x] 改成mlx-whisper（2026-04-01）：BACKEND=mlx, MODEL_NAME=large-v3，补 initial_prompt
- [x] 长句识别不准（2026-04-01）：模型大小问题，medium → large；后续切 mlx-whisper 后速度可跟上
  
P2
- [ ] 流式输出