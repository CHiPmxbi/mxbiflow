from mxbi.models.task import TaskEnum
from mxbi.tasks.cross_modal.stage import CrossModalTask
from mxbi.tasks.default.error_task.error_scene import ErrorScene
from mxbi.tasks.default.idle_task.idle_scene import IDLEScene
from mxbi.tasks.default.initial_habituation_training.stages.initial_habituation_training_stage import (
    InitialHabituationTrainingStage,
)
from mxbi.tasks.GNGSiD.stages.detect_stage.detect_stage import GNGSiDDetectStage
from mxbi.tasks.GNGSiD.stages.discriminate_stage.discriminate_stage import (
    GNGSiDDiscriminateStage,
)
from mxbi.tasks.GNGSiD.stages.size_reduction_stage.size_reduction_stage import (
    SizeReductionStage,
)
from mxbi.tasks.task_protocol import Task
from mxbi.tasks.two_alternative_choice.stages.size_reduction_stage.size_reduction_stage import (
    TWOACSizeReductionStage,
)

task_table: dict[TaskEnum, type[Task]] = {
    TaskEnum.IDEL: IDLEScene,
    TaskEnum.ERROR: ErrorScene,
    TaskEnum.HABITUATION: InitialHabituationTrainingStage,
    TaskEnum.GNGSiD_SIZE_REDUCTION_STAGE: SizeReductionStage,
    TaskEnum.GNGSiD_DETECT_STAGE: GNGSiDDetectStage,
    TaskEnum.GNGSiD_DISCRIMINATE_STAGE: GNGSiDDiscriminateStage,
    TaskEnum.TWOAC_SIZE_REDUCTION_STAGE: TWOACSizeReductionStage,
    TaskEnum.CROSS_MODAL: CrossModalTask,
}
