"""Limiti condivisi fra interfaccia, API e generazione."""
DEFAULT_CONTEXT=1024
MIN_CONTEXT=128
MAX_CONTEXT=8192

def validate_context(value=DEFAULT_CONTEXT, model_limit=None):
    maximum=min(MAX_CONTEXT,model_limit) if model_limit else MAX_CONTEXT
    if isinstance(value,bool) or not isinstance(value,int) or not MIN_CONTEXT<=value<=maximum:
        raise ValueError(f'context_window deve essere un intero fra {MIN_CONTEXT} e {maximum} token.')
    return value

def generation_budget(prompt_tokens,max_new_tokens,context_window,model_limit=None):
    context_window=validate_context(context_window,model_limit)
    if prompt_tokens>=context_window:
        raise ValueError(f'La conversazione occupa {prompt_tokens} token; il limite scelto è {context_window}. Aumenta il contesto o inizia una nuova chat.')
    return min(max_new_tokens,context_window-prompt_tokens)
