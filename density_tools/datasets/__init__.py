from datasets import visdrone, underwater


def get_dataset(db_name, db_root):
    if db_name in ['VisDrone', 'visdrone', 'VisDrone']:
        return visdrone.VisDrone(db_root)

    elif db_name.lower() == 'underwater':
        return underwater.UnderWater(db_root)

    else:
        raise NotImplementedError
