%% 自动生成音频播放列表 (Playlist Generator)
clear; clc;

% =========================================================
% 1. 配置参数 (请根据你的实际情况修改)
% =========================================================
% 你的音频文件夹路径
audioFolder = 'E:\Dataset_Audio_EEG\My_data\output\'; 

% 生成的 txt 播放列表保存到哪个文件夹？(如果没有，会自动创建)
outputFolder = 'E:\Dataset_Audio_EEG\My_data\Playlists'; 

% 核心参数设置
numTrialsPerList = 32;  % 每个 txt 文件里需要包含多少个 Trial (音频文件)？
numListsToGenerate = 5; % 你一共想生成几个这样的 txt 列表文件？

% =========================================================
% 2. 读取并检查音频文件
% =========================================================
% 获取文件夹下所有的 .wav 文件信息
wavFiles = dir(fullfile(audioFolder, '*.wav'));
totalWavCount = length(wavFiles);

fprintf('正在扫描音频文件夹: %s\n', audioFolder);
fprintf('共发现 %d 个 .wav 文件。\n\n', totalWavCount);

% 检查数量是否足够
if totalWavCount < numTrialsPerList
    error('错误：你要求的每个列表音频数 (%d) 超过了文件夹里实际拥有的音频总数 (%d)！', ...
          numTrialsPerList, totalWavCount);
end

% 如果输出文件夹不存在，则自动创建
if ~exist(outputFolder, 'dir')
    mkdir(outputFolder);
end

% =========================================================
% 3. 循环生成随机列表文件
% =========================================================
fprintf('开始生成随机播放列表...\n');

for i = 1:numListsToGenerate
    % 核心逻辑：从总数中不重复地随机抽取 numTrialsPerList 个索引
    randIdx = randperm(totalWavCount, numTrialsPerList);
    
    % 基于 Trial 数量和序列号命名文件
    % 例如: Sequence_20Trials_List01.txt
    listFileName = sprintf('Sequence_%02dTrials_List%02d.txt', numTrialsPerList, i);
    fullSavePath = fullfile(outputFolder, listFileName);
    
    % 打开文件准备写入 (强制使用 UTF-8，防止中文路径乱码)
    fid = fopen(fullSavePath, 'w', 'n', 'UTF-8');
    if fid == -1
        error('无法创建文件：%s，请检查路径权限。', fullSavePath);
    end
    
    % 写入绝对路径
    for j = 1:numTrialsPerList
        % 拼接出完整的绝对路径
        absoluteWavPath = fullfile(audioFolder, wavFiles(randIdx(j)).name);
        % 写入文件并换行
        fprintf(fid, '%s\n', absoluteWavPath);
    end
    
    % 关闭并保存文件
    fclose(fid);
    
    fprintf('  [√] 已生成: %s\n', listFileName);
end

fprintf('\n>>> 成功！全部 %d 个播放列表已保存至:\n%s\n', numListsToGenerate, outputFolder);