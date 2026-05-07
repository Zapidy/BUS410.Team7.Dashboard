# Lever Methodology

## High-level explanation

The scenario levers are model sensitivity estimates, not causal guarantees.

They do not claim that opening one branch, adding one microlender, or changing one program mechanically changes credit desert risk by an exact amount. Instead, they answer a narrower question:

If a county or tract looked more or less like places with stronger access signals, how would the model's predicted risk move?

The levers use the Influenceable model because that model was trained only on lending-environment variables that could plausibly be moved or affected by policy: branch access, mission-lender presence, microlender coverage, state credit-support programs, and lender concentration.

## The plain-English weighting idea

Each lever gets its strength from two questions:

1. How much does the model depend on this category of variables?
2. Within that category, how important is this exact slider variable?

That first question is the key one. We test it by temporarily taking away a whole category from the model and seeing how much worse the model gets. If the model gets much worse without that category, the dashboard treats the category as more important.

In technical language, that is an ablation test. For a panel, the simpler phrase is:

> We remove one category at a time and see how much the model misses it.

## What changed

The dashboard originally used two different formulas:

- The map and scenario counters used the remove-one-category test as a flat percentage-point shift.
- The drawer risk percentages used feature importance as a log-odds shift.

That made the dashboard internally inconsistent. A lever could recolor the map while the drawer barely moved, or the drawer could move differently from the map.

The methodology now uses one unified sensitivity formula everywhere:

- map color
- scenario counters
- tract drawer risk percentages
- county drawer risk percentages

## How each lever gets its weight

First, the dashboard checks the lever category.

Examples:

- branch access
- MDI / mission-lender presence
- microlender ecosystem
- state credit-support programs
- lender concentration

If removing one of those categories makes the model worse, that category gets more scenario weight.

Second, the dashboard checks the specific feature inside the category.

For example, branch access is a category. Inside that category:

- distance to nearest bank branch carries more weight
- branches within 5 miles carries less weight

So both sliders belong to branch access, but they do not receive equal scenario influence.

## Direction of each lever

The sign of each lever follows the model's learned direction:

- Greater bank branch distance increases risk.
- More nearby branches decreases risk.
- More MDI branch reach decreases risk.
- More microlender coverage decreases risk.
- More SSBCI program coverage generally decreases risk, but it is weaker and more contextual.
- Higher residualized lender concentration increases risk.

## How the risk percentage changes

The lever effect is applied on a log-odds scale, then converted back to a normal risk percentage.

That matters because risk is bounded between 0% and 100%. A lever should not move a place from 98% to 120%, and the same model signal should not have exactly the same visible percentage-point effect at every starting risk level.

In plain language:

1. Start with the current predicted risk.
2. Convert it into a form where risk can move up or down safely.
3. Add the scenario sensitivity effect.
4. Convert it back into a risk percentage.

## Diagnostic vs. Influenceable

The Influenceable model gets the full scenario effect because its inputs are the variables the levers represent.

The Diagnostic model gets a damped effect. It uses many structural and diagnostic predictors that are not directly policy-controllable, so the lever should affect it less.

## How to explain this to a panel

The safest explanation is:

> These levers are not causal policy simulations. They are model sensitivity estimates. We first ask how much the model depends on a whole category, like branch access or microlenders. Then we ask how important this exact slider is inside that category. Moving a lever shows how predicted credit desert risk changes when the place is made to look more or less like places with stronger access conditions.

Short version:

> The levers show model-supported sensitivity, not guaranteed policy impact.

