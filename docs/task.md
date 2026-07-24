## Task 📋

### _Task_, _Step_, _Milestone_

Understanding the relationship between these three concepts is **crucial**. Each `task` may contain some parameters to control difficulty, and these parameters change as `steps` progress. However, should a `task` hold `milestones`? I believe it's **unnecessary**. I think `milestones` often signify **significant changes** in task logic, and changes in task logic typically mean the task should be split into multiple tasks. Therefore, `milestones` should be managed by the `scheduler` to switch between different tasks rather than steps within a task. 🔄

### What is a _task_? 🤔

For me, a `task` contains some parameters that can control difficulty, but apart from handling different outcomes, it doesn't create new logical branches - its input and output should remain **stable**. When the difficulty increases to a certain point, reaching a `milestone`, we directly switch to the corresponding task. ⬆️

Therefore, a `task` that can be scheduled by a `Scheduler` should include the following: 📝

1. **Difficulty configuration table** 📊, recording parameters that change with the increase of `level` (`step`)

```python
class LevelConfig(BaseModel):
    level: int  # Current difficulty level
    stimulation_size: int  # Variable parameter
    min_sound_span: float  # Variable parameter
    max_sound_span: float  # Variable parameter
    reward_delay: float  # Variable parameter
    visual_stimulus_delay: float  # Variable parameter


class LevelConfigs(RootModel):
    root: dict[int, LevelConfig]  # Records different parameters by difficulty level
```

2. **Scheduling logic** ⚙️

```python
class ScheduleCondition(BaseModel):
    level_count: int = 0  # Total number of difficulty levels
    evaluation_interval: int = 20  # Evaluate accuracy every N trials
    difficulty_increase_threshold: float = (
        0.8  # Increase difficulty if accuracy exceeds this value
    )
    difficulty_decrease_threshold: float = (
        0.45  # Decrease difficulty if accuracy falls below this value
    )
    next_task: TaskEnum = TaskEnum.IDEL  # What is the next task


class TrialConfig(BaseModel):
    condition: ScheduleCondition = Field(
        default_factory=lambda: ScheduleCondition(
            level_count=12,
        )
    )
    stimulus_frequency: int = 2000  # Constant parameter
    time_out: int = 10000  # Constant parameter
```

The `Scheduler` will decide how to schedule tasks based on the `ScheduleCondition` provided by the `Task`. 🎯

finally, a complete configuration file would be:

```json
// config_trial.json
{
  "condition": {
    "level_count": 12,
    "evaluation_interval": 20,
    "difficulty_increase_threshold": 0.8,
    "difficulty_decrease_threshold": 0.45,
    "next_task": "idel"
  },
  "stimulus_frequency": 2000,
  "time_out": 10000,
  "level_config": null
}
```

```json
// config_levels.json
{
  "0": {
    "level": 0,
    "stimulation_size": 430,
    "min_sound_span": 1.0,
    "max_sound_span": 1.0,
    "reward_delay": 0.0,
    "visual_stimulus_delay": 0.0
  },
  "1": {
    "level": 1,
    "stimulation_size": 420,
    "min_sound_span": 1.0,
    "max_sound_span": 1.0,
    "reward_delay": 0.0,
    "visual_stimulus_delay": 0.0
  },
  "2": {
    "level": 0,
    "stimulation_size": 400,
    "min_sound_span": 1.0,
    "max_sound_span": 1.0,
    "reward_delay": 0.1,
    "visual_stimulus_delay": 0.0
  },
  {
    ...
  },
  "11": {
    "level": 0,
    "stimulation_size": 380,
    "min_sound_span": 1.0,
    "max_sound_span": 1.0,
    "reward_delay": 0.2,
    "visual_stimulus_delay": 0.0
  }
}
```

This means that during task execution: the `scheduler` evaluates accuracy **every 20 trials** 📊. If accuracy **exceeds 80%** ⬆️, difficulty increases; if accuracy **falls below 45%** ⬇️, difficulty decreases. The `task` has a total of **12 difficulty levels** 🎚️, with each level corresponding to different parameter configurations. Once this `task` is completed, it will switch to `TaskEnum.IDEL`. ✅
