'''
Implementation of a Gurobi based solver interface.

'''
from collections import OrderedDict
from .solver import Solver, Solution, Status
from gurobipy import setParam, Model as GurobiModel, GRB, quicksum

setParam("OutputFlag", 0)

status_mapping = {GRB.OPTIMAL: Status.OPTIMAL,
                  GRB.UNBOUNDED: Status.UNBOUNDED,
                  GRB.INFEASIBLE: Status.UNFEASIBLE}


class GurobiSolver(Solver):
    """ Implements the solver interface using gurobipy. """
    
    def __init__(self):
        Solver.__init__(self)

        
    def build_problem(self, model):
        """ Implements method from Solver class. """
        
        problem = GurobiModel()
        
        #create variables
        lpvars = {r_id: problem.addVar(name=r_id,
                                       lb=lb if lb is not None else -GRB.INFINITY,
                                       ub=ub if ub is not None else GRB.INFINITY)
                  for r_id, (lb, ub) in model.bounds.items()}
        
        problem.update() #confirm if really necessary
        
        #create constraints
        for m_id in model.metabolites:
            constr = quicksum([coeff*lpvars[r_id] for (m_id2, r_id), coeff in model.stoichiometry.items()
                                 if m_id2 == m_id])
            problem.addConstr(constr == 0, m_id)

        self.problem = problem
        self.var_ids = model.reactions.keys()
        self.constr_ids = model.metabolites.keys()
                
    def solve_lp(self, objective, model=None, constraints=None, get_shadow_prices=False, get_reduced_costs=False):
        """ Implements method from Solver class. """
        
        return self._generic_solve(None, objective, GRB.MAXIMIZE, model, constraints, get_shadow_prices, get_reduced_costs)


    def solve_qp(self, quad_obj, lin_obj, model=None, constraints=None, get_shadow_prices=False, get_reduced_costs=False):
        """ Implements method from Solver class. """
        
        return self._generic_solve(quad_obj, lin_obj, GRB.MINIMIZE, model, constraints, get_shadow_prices, get_reduced_costs)

    
    def _generic_solve(self, quad_obj, lin_obj, sense, model=None, constraints=None, get_shadow_prices=False, get_reduced_costs=False):
        
        if model: 
            self.build_problem(model)

        if self.problem:
            problem = self.problem
        else:
            raise Exception('A model must be given if solver is used for the first time.')
        
        if constraints:
            old_constraints = {}
            for r_id, (lb, ub) in constraints.items():
                lpvar = problem.getVarByName(r_id)
                old_constraints[r_id] = (lpvar.lb, lpvar.ub)
                lpvar.lb = lb if lb is not None else -GRB.INFINITY
                lpvar.ub = ub if ub is not None else GRB.INFINITY
            problem.update()
        
        #create objective function
        quad_obj_expr = [q*problem.getVarByName(r_id1)*problem.getVarByName(r_id2)
                        for (r_id1, r_id2), q in quad_obj.items() if q] if quad_obj else []
        lin_obj_expr = [f*problem.getVarByName(r_id)
                        for r_id, f in lin_obj.items() if f] if lin_obj else []
        obj_expr = quicksum(quad_obj_expr + lin_obj_expr)
        problem.setObjective(obj_expr, sense)

        #run the optimization
        problem.optimize()
        status = status_mapping[problem.status] if problem.status in status_mapping else Status.UNKNOWN
        
        if status == Status.OPTIMAL:
            fobj = problem.ObjVal
            values = OrderedDict([(r_id, problem.getVarByName(r_id).X) for r_id in self.var_ids])
            shadow_prices = OrderedDict([(m_id, problem.getConstrByName(m_id).Pi) for m_id in self.constr_ids]) if get_shadow_prices else None
            reduced_costs = OrderedDict([(r_id, problem.getVarByName(r_id).RC) for r_id in self.var_ids]) if get_reduced_costs else None
            solution = Solution(status, fobj, values, shadow_prices, reduced_costs)
        else:
            solution = Solution(status)
        
        #reset old constraints because temporary constraints should not be persistent
        if constraints:
            for r_id, (lb, ub) in old_constraints.items():
                lpvar = problem.getVarByName(r_id)
                lpvar.lb, lpvar.ub = lb, ub
            problem.update()
                    
        return solution