from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class OperatingSettings(StrictModel):
    machine_load: float = Field(.7, ge=.25, le=1)
    machine_speed: float = Field(1200, ge=600, le=1800)
    power_factor: float = Field(.90, ge=.80, le=.99)


class OperatingPoint(OperatingSettings):
    temperature: float = Field(32, ge=20, le=45)
    energy_kwh: float | None = Field(None, ge=0, le=500, description='Optional observed energy; never a prediction input')


class OptimizeRequest(StrictModel):
    temperature: float = Field(32, ge=20, le=45)
    tariff: float = Field(.8, gt=0, le=10, description='Illustrative currency units/kWh')
    min_production_rate: float = Field(12, ge=1, le=45)
    max_energy_kwh: float = Field(50, ge=1, le=100)
    reference: OperatingSettings = Field(default_factory=OperatingSettings, description='Baseline settings for the same-output comparison')
    weights: list[float] = Field(default_factory=lambda: [1, 1, 1], min_length=3, max_length=3)
    population: int = Field(80, ge=40, le=160)
    generations: int = Field(70, ge=20, le=150)
    seed: int = Field(42, ge=0, le=2147483647)

    @model_validator(mode='after')
    def valid_weights(self):
        import math
        if not all(math.isfinite(w) and w >= 0 for w in self.weights) or sum(self.weights) <= 0:
            raise ValueError('Weights must be finite, nonnegative and have positive sum')
        return self


class ControlSettings(StrictModel):
    target: float = Field(22, ge=8, le=38, description='Initial production setpoint, units/hour')
    target_after: float = Field(28, ge=8, le=38)
    steps: int = Field(36, ge=12, le=72)
    target_step: int = Field(10, ge=1, le=70)
    disturbance_step: int = Field(20, ge=1, le=70)
    disturbance_enabled: bool = True
    material_factor: float = Field(.82, ge=.7, le=1.15)
    ambient: float = Field(30, ge=20, le=35)
    tariff: float = Field(.8, gt=0, le=5)
    max_energy_kwh: float = Field(45, ge=5, le=65)
    max_temperature: float = Field(55, ge=35, le=70)
    energy_weight: float = Field(.5, ge=0, le=5)
    horizon: int = Field(5, ge=2, le=8)
    samples: int = Field(128, ge=32, le=256)
    iterations: int = Field(3, ge=2, le=5)
    seed: int = Field(42, ge=0, le=2147483646)

    @model_validator(mode='after')
    def check_timing_and_budget(self):
        if self.target_step >= self.steps or self.disturbance_step >= self.steps:
            raise ValueError('Setpoint and disturbance steps must be smaller than the number of simulation steps')
        if self.steps*self.horizon*self.samples*self.iterations > 300000:
            raise ValueError('Simulation search budget exceeds 300,000 model steps; reduce steps, horizon, samples or iterations')
        return self


class ControlStepRequest(StrictModel):
    state: list[float] = Field(default_factory=lambda: [.7,1200,.9,40,21,21],min_length=6,max_length=6)
    previous_command: list[float] = Field(default_factory=lambda: [.7,1200,.9],min_length=3,max_length=3)
    target: float = Field(28,ge=8,le=38)
    ambient: float = Field(30,ge=20,le=38)
    material_factor: float = Field(1,ge=.7,le=1.2)
    tariff: float = Field(.8,gt=0,le=5)
    max_energy_kwh: float = Field(45,ge=5,le=65)
    max_temperature: float = Field(55,ge=35,le=70)
    energy_weight: float = Field(.5,ge=0,le=5)
    horizon: int = Field(5,ge=2,le=8)
    samples: int = Field(128,ge=32,le=256)
    iterations: int = Field(3,ge=2,le=5)
    seed: int = Field(42,ge=0,le=2147483647)

    @model_validator(mode='after')
    def check_state(self):
        import math
        from .plant import STATE_LOW, STATE_HIGH, COMMAND_LOW, COMMAND_HIGH
        for values, low, high in [(self.state,STATE_LOW,STATE_HIGH),(self.previous_command,COMMAND_LOW,COMMAND_HIGH)]:
            if any(not math.isfinite(v) or v < lo or v > hi for v,lo,hi in zip(values,low,high)):
                raise ValueError('Measured state or previous command is outside supported finite bounds')
        return self
