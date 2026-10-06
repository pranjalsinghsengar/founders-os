"""Bounded hosted-search profiles, not a separate deep-research provider."""

def research_profile(config, mode='normal'):
    if mode not in ('normal', 'deep'):
        raise ValueError('Research mode must be normal or deep')
    prefix = 'research_' if mode == 'normal' else 'deep_research_'
    defaults = (30, 4, 6000) if mode == 'normal' else (60, 8, 10000)
    profile = dict(zip(('cost_units', 'max_search_calls', 'max_output_tokens'),
                       [config.get(prefix + key, default) for key, default in
                        zip(('cost_units', 'max_search_calls', 'max_output_tokens'), defaults)]))
    for key, maximum in (('cost_units', 100000), ('max_search_calls', 8), ('max_output_tokens', 32000)):
        value = profile[key]
        if type(value) is not int or not (0 if key == 'cost_units' else 1) <= value <= maximum:
            raise ValueError('Invalid research profile: ' + key)
    return {'mode': mode, **profile}
