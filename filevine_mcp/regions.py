"""Fail closed when selecting a credential-bearing region."""


def region_config(region, regions):
    region = region.strip().lower()
    if region not in regions:
        raise ValueError("Unsupported region; choose one of: " + ", ".join(regions))
    return regions[region]
