from lib.pipelines.pipelinelog import PipelineLog

class PipelineInfo:

    @staticmethod
    def get(process_uid:str):
        process = PipelineInfo.getPipelineInfo(process_uid=process_uid)
        if process is None:
            return None

        process = dict(process)
        steps = []
        for step in PipelineInfo.getPipelineSteps(pipeline_process_id=process["id"]):
            step = dict(step)
            step.pop("logs", None)
            steps.append(step)

        is_ended = process["is_success"] is not None

        return {
            "pipeline_uid" : process["pipeline_uid"],
            "process_uid" : process_uid,
            "created_at" : process["created_at"] or "",
            "started_at" : process["started_at"] or "",
            "ended_at" : process["ended_at"] or "",
            "is_ended" : is_ended,
            "is_success" : bool(process["is_success"]) if process["is_success"] is not None else False,
            "steps" : steps
        }

    @staticmethod
    def getStep(process_uid:str, step_id:int):
        process = PipelineInfo.getPipelineInfo(process_uid=process_uid)
        if process is None:
            return None

        process = dict(process)
        step = PipelineInfo.getPipelineStep(pipeline_block_id=step_id)
        if step is None:
            return None

        step = dict(step)
        if step["pipeline_process_id"] != process["id"]:
            return None

        return {
            "id" : step["id"],
            "process_uid" : process_uid,
            "pipeline_uid" : process["pipeline_uid"],
            "name" : step["name"],
            "created_at" : step["created_at"] or "",
            "is_success" : bool(step["is_success"]) if step["is_success"] is not None else False,
            "logs" : step["logs"] or ""
        }

    @staticmethod
    def getPipelineInfo(process_uid:str):
        return PipelineLog.getProcess(process_uid=process_uid)

    @staticmethod
    def getPipelineSteps(pipeline_process_id:int):
        return PipelineLog.getBlocks(pipeline_process_id=pipeline_process_id)

    @staticmethod
    def getPipelineStep(pipeline_block_id:int):
        return PipelineLog.getBlock(block_id=pipeline_block_id)
